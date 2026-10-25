#!/usr/bin/env python3
"""
ENT1K-3: 1000-User Scale & Concurrency Test Suite for CortexForge.

Covers:
1. test_1000_users_quota_proxy_concurrent_and_sse:
   - Registers 1,000 users (user-1..user-1000 across dept-0..dept-9) in a live quota-proxy
   - Runs 1,000 concurrent requests across ThreadPoolExecutor(max_workers=64) mixing
     standard JSON responses, Anthropic SSE streams, and OpenAI SSE streams
   - Verifies 0 HTTP 500s and 0 sqlite3.OperationalError ("database is locked")
   - Verifies exact token accounting across all 1,000 users and all 10 departments
   - Verifies report pagination (GET /quota/report?limit=100&offset=...) and
     department filtering (?department=dept-0)
   - Verifies department quota enforcement (POST /quota/set-department-limit)

2. test_1000_agents_broker_concurrent_messaging_and_broadcast:
   - Registers 1,000 agents (user-1..user-1000) in a live message-broker
   - Runs 1,100+ concurrent P2P messages across ThreadPoolExecutor(max_workers=64)
     plus admin POST /broadcast to "*" (all 1,000 agents)
   - Verifies GET /inbox/all?limit=100&offset=0 pagination (total_inboxes == 1000)
   - Verifies GET /inbox?peek=1 non-destructive reads, priority ordering, and zero
     lost messages or database lock errors

3. test_bulk_provision_1000_users_manifest:
   - Generates a 1,000-user manifest in a temporary repository root
   - Executes scripts/bulk-users.py import --file ... --shard-size 100
   - Verifies all 1,000 instances, .env keys, and 10 compose shards (shard-0..shard-9)
     are created rapidly with zero port collisions
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import json
import os
import pathlib
import shutil
import sqlite3
import stat
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
PROXY_PATH = REPO_ROOT / "quota-proxy" / "proxy.py"
BROKER_DIR = REPO_ROOT / "broker"
BULK_SCRIPT_PATH = REPO_ROOT / "scripts" / "bulk-users.py"


class HighConcurrencyHTTPServer(ThreadingHTTPServer):
    """ThreadingHTTPServer with a larger socket backlog for 64+ concurrent workers."""

    request_queue_size = 512
    allow_reuse_address = True
    daemon_threads = True


class MockScaleUpstreamHandler(BaseHTTPRequestHandler):
    """Mock LLM upstream supporting JSON, Anthropic SSE, and OpenAI SSE streams."""

    def log_message(self, fmt, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {}

        mode = payload.get("mock_mode", "json")
        in_tok = int(payload.get("in_tok", 10))
        out_tok = int(payload.get("out_tok", 20))

        if mode == "sse_anthropic":
            stream_bytes = (
                "event: message_start\n"
                f'data: {{"type":"message_start","message":{{"id":"msg_a","usage":{{"input_tokens":{in_tok},"output_tokens":1}}}}}}\n\n'
                "event: content_block_delta\n"
                'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"ok"}}\n\n'
                "event: message_delta\n"
                f'data: {{"type":"message_delta","delta":{{"stop_reason":"end_turn"}},"usage":{{"output_tokens":{out_tok}}}}}\n\n'
                "event: message_stop\n"
                'data: {"type":"message_stop"}\n\n'
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.end_headers()
            self.wfile.write(stream_bytes)
            self.wfile.flush()
            return

        if mode == "sse_openai":
            stream_bytes = (
                'data: {"id":"chatcmpl-scale","choices":[{"index":0,"delta":{"content":"ok"}}]}\n\n'
                f'data: {{"id":"chatcmpl-scale","choices":[],"usage":{{"prompt_tokens":{in_tok},"completion_tokens":{out_tok},"total_tokens":{in_tok + out_tok}}}}}\n\n'
                "data: [DONE]\n\n"
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(stream_bytes)
            self.wfile.flush()
            return

        body = json.dumps(
            {
                "id": "msg_json_scale",
                "type": "message",
                "usage": {"input_tokens": in_tok, "output_tokens": out_tok},
            }
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _load_module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestScale1000Users(unittest.TestCase):
    """End-to-end 1000-user concurrency and scale verification (ENT1K-3)."""

    # ── Test 1: 1000 Concurrent Users in Quota-Proxy (JSON + SSE) ─────────

    def test_1000_users_quota_proxy_concurrent_and_sse(self):
        saved_env = dict(os.environ)
        tmpdir = tempfile.mkdtemp(prefix="ent1k_quota_1000_")
        db_path = os.path.join(tmpdir, "quota_1000.db")
        admin_token = "adm-" * 8

        upstream_srv = HighConcurrencyHTTPServer(("127.0.0.1", 0), MockScaleUpstreamHandler)
        upstream_port = upstream_srv.server_address[1]
        upstream_thread = threading.Thread(target=upstream_srv.serve_forever, daemon=True)
        upstream_thread.start()

        proxy_srv = None
        proxy_mod = None
        try:
            os.environ["QUOTA_DB"] = db_path
            os.environ["UPSTREAM_URL"] = f"http://127.0.0.1:{upstream_port}"
            os.environ["UPSTREAM_API_KEY"] = "mock"
            os.environ["QUOTA_ADMIN_TOKEN"] = admin_token
            os.environ["QUOTA_DEFAULT_MONTHLY"] = "1000000"

            proxy_mod = _load_module("quota_proxy_scale_1000", PROXY_PATH)
            proxy_mod._admin_rl = proxy_mod.RateLimiter(rate=100_000.0, capacity=100_000)
            proxy_mod._proxy_rl = proxy_mod.RateLimiter(rate=100_000.0, capacity=100_000)
            proxy_mod.Handler.log_message = lambda self, fmt, *a: None

            proxy_srv = HighConcurrencyHTTPServer(("127.0.0.1", 0), proxy_mod.Handler)
            proxy_port = proxy_srv.server_address[1]
            proxy_thread = threading.Thread(target=proxy_srv.serve_forever, daemon=True)
            proxy_thread.start()

            base_url = f"http://127.0.0.1:{proxy_port}"

            def admin_req(method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
                headers = {
                    "Authorization": f"Bearer {admin_token}",
                    "Content-Type": "application/json",
                }
                data = json.dumps(payload).encode("utf-8") if payload is not None else None
                req = urllib.request.Request(
                    f"{base_url}{path}", data=data, headers=headers, method=method
                )
                try:
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        return resp.status, json.loads(resp.read().decode("utf-8"))
                except urllib.error.HTTPError as err:
                    with err:
                        return err.code, json.loads(err.read().decode("utf-8"))

            def proxy_req(quota_key: str, payload: dict) -> tuple[int, bytes]:
                headers = {
                    "x-api-key": quota_key,
                    "Content-Type": "application/json",
                }
                data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    f"{base_url}/v1/messages", data=data, headers=headers, method="POST"
                )
                try:
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        return resp.status, resp.read()
                except urllib.error.HTTPError as err:
                    with err:
                        return err.code, err.read()

            # 1. Register 1,000 users (user-1..user-1000) across 10 departments (dept-0..dept-9)
            num_users = 1000
            expected_user_tokens: dict[str, tuple[int, int, str]] = {}
            expected_dept_tokens: dict[str, dict[str, int]] = {
                f"dept-{d}": {"input": 0, "output": 0, "total": 0, "requests": 0, "instances": 0}
                for d in range(10)
            }

            for i in range(1, num_users + 1):
                inst = f"user-{i}"
                dept = f"dept-{(i - 1) % 10}"
                if i % 3 == 1:
                    in_tok, out_tok = 12 + (i % 7), 18 + (i % 5)
                elif i % 3 == 2:
                    in_tok, out_tok = 35 + (i % 11), 45 + (i % 9)
                else:
                    in_tok, out_tok = 50 + (i % 13), 25 + (i % 7)
                expected_user_tokens[inst] = (in_tok, out_tok, dept)
                expected_dept_tokens[dept]["input"] += in_tok
                expected_dept_tokens[dept]["output"] += out_tok
                expected_dept_tokens[dept]["total"] += in_tok + out_tok
                expected_dept_tokens[dept]["requests"] += 1
                expected_dept_tokens[dept]["instances"] += 1

            def register_one(i: int) -> tuple[int, str]:
                inst = f"user-{i}"
                dept = f"dept-{(i - 1) % 10}"
                key = f"q-{i}"
                try:
                    code, _ = admin_req(
                        "POST",
                        "/quota/register-key",
                        {
                            "instance": inst,
                            "quota_key": key,
                            "department": dept,
                            "limit": 1_000_000,
                        },
                    )
                    return code, ""
                except Exception as exc:
                    return 599, str(exc)

            with ThreadPoolExecutor(max_workers=64) as pool:
                reg_results = list(pool.map(register_one, range(1, num_users + 1)))

            reg_errors = [r for r in reg_results if r[0] != 200]
            self.assertEqual(
                len(reg_errors),
                0,
                f"Expected 0 registration failures across 1000 users, got: {reg_errors[:5]}",
            )

            # 2. Execute 1,000 concurrent requests (JSON + Anthropic SSE + OpenAI SSE) with 64 workers
            def invoke_user(i: int) -> tuple[int, int, str]:
                inst = f"user-{i}"
                key = f"q-{i}"
                in_tok, out_tok, _ = expected_user_tokens[inst]
                if i % 3 == 1:
                    mode = "json"
                elif i % 3 == 2:
                    mode = "sse_anthropic"
                else:
                    mode = "sse_openai"
                try:
                    code, raw = proxy_req(
                        key, {"mock_mode": mode, "in_tok": in_tok, "out_tok": out_tok}
                    )
                    return i, code, raw.decode("utf-8", errors="replace")
                except sqlite3.OperationalError as db_exc:
                    return i, 500, f"sqlite3.OperationalError: {db_exc}"
                except Exception as exc:
                    return i, 599, str(exc)

            with redirect_stdout(io.StringIO()), ThreadPoolExecutor(max_workers=64) as pool:
                call_results = list(pool.map(invoke_user, range(1, num_users + 1)))

            http_500s = [r for r in call_results if r[1] >= 500]
            db_locked = [r for r in call_results if "database is locked" in r[2].lower()]
            non_200s = [r for r in call_results if r[1] != 200]

            self.assertEqual(len(http_500s), 0, f"Expected 0 HTTP 500 errors, got {http_500s[:5]}")
            self.assertEqual(len(db_locked), 0, f"Expected 0 database lock errors, got {db_locked[:5]}")
            self.assertEqual(len(non_200s), 0, f"Expected all 1000 requests to return 200, got {non_200s[:5]}")

            # 3. Verify pagination GET /quota/report?limit=100&offset=... across all 1,000 instances
            collected_usage: dict[str, dict] = {}
            departments_summary: dict[str, dict] = {}
            for page_idx in range(10):
                offset = page_idx * 100
                code, report = admin_req("GET", f"/quota/report?limit=100&offset={offset}")
                self.assertEqual(code, 200)
                self.assertEqual(report["total_instances"], num_users)
                self.assertEqual(len(report["usage"]), 100)
                if page_idx == 0:
                    departments_summary = report["departments"]
                for row in report["usage"]:
                    collected_usage[row["instance"]] = row

            self.assertEqual(len(collected_usage), num_users)

            # Verify exact token accounting for every single user (user-1..user-1000)
            for inst, (exp_in, exp_out, exp_dept) in expected_user_tokens.items():
                self.assertIn(inst, collected_usage)
                actual = collected_usage[inst]
                self.assertEqual(actual["input_tokens"], exp_in, f"Mismatch input_tokens for {inst}")
                self.assertEqual(actual["output_tokens"], exp_out, f"Mismatch output_tokens for {inst}")
                self.assertEqual(actual["total_tokens"], exp_in + exp_out, f"Mismatch total_tokens for {inst}")
                self.assertEqual(actual["requests"], 1, f"Mismatch requests for {inst}")
                self.assertEqual(actual["department"], exp_dept, f"Mismatch department for {inst}")

            # Verify exact token accounting across all 10 departments (dept-0..dept-9)
            for dept_name, exp_d in expected_dept_tokens.items():
                self.assertIn(dept_name, departments_summary)
                act_d = departments_summary[dept_name]
                self.assertEqual(act_d["input_tokens"], exp_d["input"], f"Dept {dept_name} input mismatch")
                self.assertEqual(act_d["output_tokens"], exp_d["output"], f"Dept {dept_name} output mismatch")
                self.assertEqual(act_d["total_tokens"], exp_d["total"], f"Dept {dept_name} total mismatch")
                self.assertEqual(act_d["requests"], exp_d["requests"], f"Dept {dept_name} requests mismatch")
                self.assertEqual(act_d["instances"], exp_d["instances"], f"Dept {dept_name} instances mismatch")

            # Verify department filtering ?department=dept-0
            code, dept0_report = admin_req("GET", "/quota/report?department=dept-0")
            self.assertEqual(code, 200)
            self.assertEqual(dept0_report["total_instances"], 100)
            self.assertEqual(len(dept0_report["usage"]), 100)
            for item in dept0_report["usage"]:
                self.assertEqual(item["department"], "dept-0")

            # 4. Verify department quota limit enforcement (POST /quota/set-department-limit)
            dept0_total = expected_dept_tokens["dept-0"]["total"]
            code, limit_resp = admin_req(
                "POST",
                "/quota/set-department-limit",
                {"department": "dept-0", "limit": dept0_total},
            )
            self.assertEqual(code, 200)
            self.assertEqual(limit_resp["limit"], dept0_total)

            # user-1 belongs to dept-0 -> must now receive 429 quota_exceeded
            blocked_code, blocked_raw = proxy_req(
                "q-1", {"mock_mode": "json", "in_tok": 5, "out_tok": 5}
            )
            self.assertEqual(blocked_code, 429)
            blocked_payload = json.loads(blocked_raw.decode("utf-8"))
            self.assertEqual(blocked_payload["error"], "quota_exceeded")
            self.assertIn("dept-0", blocked_payload["message"])

            # user-2 belongs to dept-1 -> unaffected, must still succeed with 200
            ok_code, _ = proxy_req(
                "q-2", {"mock_mode": "json", "in_tok": 5, "out_tok": 5}
            )
            self.assertEqual(ok_code, 200)
        finally:
            if proxy_srv:
                proxy_srv.shutdown()
                proxy_srv.server_close()
            upstream_srv.shutdown()
            upstream_srv.server_close()
            if proxy_mod and getattr(proxy_mod, "_conn", None):
                proxy_mod._conn.close()
            os.environ.clear()
            os.environ.update(saved_env)
            shutil.rmtree(tmpdir, ignore_errors=True)

    # ── Test 2: 1000 Concurrent Agents in Broker + Broadcast ──────────────

    def test_1000_agents_broker_concurrent_messaging_and_broadcast(self):
        if str(BROKER_DIR) not in sys.path:
            sys.path.insert(0, str(BROKER_DIR))
        import broker

        saved_env = {k: v for k, v in os.environ.items() if k.startswith("BROKER_")}
        orig_db = broker.BROKER_DB
        orig_rl = broker._send_rl
        orig_log = broker.Handler.log_message
        orig_max_age = broker.MAX_AGE_SEC
        orig_retention = broker.RETENTION_SECONDS
        orig_min_ttl = broker._min_active_ttl

        tmpdir = tempfile.mkdtemp(prefix="ent1k_broker_1000_")
        db_path = os.path.join(tmpdir, "broker_1000.db")
        admin_key = "adm"

        srv = None
        try:
            for k in list(os.environ.keys()):
                if k.startswith("BROKER_"):
                    os.environ.pop(k, None)

            broker.BROKER_DB = db_path
            broker.MAX_AGE_SEC = 86400
            broker.RETENTION_SECONDS = 86400
            broker._min_active_ttl = 86400.0
            broker._last_purge_ts = 0.0
            os.environ["BROKER_DB"] = db_path
            os.environ["BROKER_KEY_ADMIN"] = admin_key

            broker._init_db()
            broker._load_keys()
            broker._send_rl = broker.RateLimiter(rate=100_000.0, capacity=100_000)
            broker.Handler.log_message = lambda self, fmt, *a: None

            srv = HighConcurrencyHTTPServer(("127.0.0.1", 0), broker.Handler)
            port = srv.server_address[1]
            threading.Thread(target=srv.serve_forever, daemon=True).start()

            base_url = f"http://127.0.0.1:{port}"

            def broker_req(method: str, path: str, payload: dict | None = None, key: str | None = None) -> tuple[int, dict]:
                headers = {"Content-Type": "application/json"}
                if key:
                    headers["Authorization"] = f"Bearer {key}"
                data = json.dumps(payload).encode("utf-8") if payload is not None else None
                req = urllib.request.Request(
                    f"{base_url}{path}", data=data, headers=headers, method=method
                )
                try:
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        return resp.status, json.loads(resp.read().decode("utf-8"))
                except urllib.error.HTTPError as err:
                    with err:
                        return err.code, json.loads(err.read().decode("utf-8"))

            num_agents = 1000

            # 1. Register 1,000 agents (user-1..user-1000) concurrently
            def register_agent(i: int) -> int:
                code, _ = broker_req(
                    "POST",
                    "/admin/register-key",
                    {"instance": f"user-{i}", "broker_key": f"brk-agent-{i}-key"},
                    key=admin_key,
                )
                return code

            with ThreadPoolExecutor(max_workers=64) as pool:
                reg_codes = list(pool.map(register_agent, range(1, num_agents + 1)))

            self.assertTrue(
                all(c == 200 for c in reg_codes),
                "All 1,000 agent key registrations must succeed with HTTP 200",
            )

            # 2. Send 1,100 concurrent P2P messages across agents
            #    - 1,000 ring messages: user-i -> user-((i % 1000) + 1)
            #    - 100 extra priority messages: user-(i + 500) -> user-i for i in 1..100
            tasks: list[tuple[int, str, str, str]] = []
            priorities = ("low", "normal", "high", "urgent")
            for i in range(1, num_agents + 1):
                target = f"user-{(i % num_agents) + 1}"
                tasks.append((i, target, f"ring-msg-from-{i}", priorities[i % 4]))
            for i in range(1, 101):
                tasks.append((i + 500, f"user-{i}", f"cross-high-msg-{i}", "high"))

            def send_task(item: tuple[int, str, str, str]) -> tuple[int, str]:
                sender_idx, target, text, prio = item
                try:
                    code, body = broker_req(
                        "POST",
                        "/send",
                        {"to": target, "message": text, "priority": prio},
                        key=f"brk-agent-{sender_idx}-key",
                    )
                    return code, json.dumps(body)
                except sqlite3.OperationalError as db_exc:
                    return 500, f"sqlite3.OperationalError: {db_exc}"
                except Exception as exc:
                    return 599, str(exc)

            with redirect_stdout(io.StringIO()), ThreadPoolExecutor(max_workers=64) as pool:
                send_results = list(pool.map(send_task, tasks))

            send_failures = [r for r in send_results if r[0] != 200]
            lock_errors = [r for r in send_results if "database is locked" in r[1].lower()]
            self.assertEqual(len(lock_errors), 0, f"Expected 0 database lock errors, got {lock_errors[:5]}")
            self.assertEqual(len(send_failures), 0, f"Expected all 1,100 sends to return 200, got {send_failures[:5]}")

            # 3. Admin broadcast to "*" (all 1,000 agents)
            b_code, b_body = broker_req(
                "POST",
                "/broadcast",
                {"to": "*", "text": "Broadcast alert to all 1000 agents", "priority": "urgent"},
                key=admin_key,
            )
            self.assertEqual(b_code, 200)
            self.assertTrue(b_body["ok"])
            self.assertEqual(b_body["delivered_count"], num_agents)

            # 4. Verify paginated GET /inbox/all?limit=100&offset=... across all 10 pages
            all_inbox_counts: dict[str, int] = {}
            for page_idx in range(10):
                offset = page_idx * 100
                code, page = broker_req(
                    "GET", f"/inbox/all?limit=100&offset={offset}", key=admin_key
                )
                self.assertEqual(code, 200)
                self.assertEqual(page["total_inboxes"], num_agents)
                self.assertEqual(len(page["inboxes"]), 100)
                all_inbox_counts.update(page["inboxes"])

            self.assertEqual(len(all_inbox_counts), num_agents)
            # Total undelivered messages must be exactly 1,100 (P2P) + 1,000 (broadcast) = 2,100
            self.assertEqual(sum(all_inbox_counts.values()), 2100)
            for i in range(1, num_agents + 1):
                expected_cnt = 3 if i <= 100 else 2
                self.assertEqual(
                    all_inbox_counts.get(f"user-{i}"),
                    expected_cnt,
                    f"Agent user-{i} expected {expected_cnt} messages, got {all_inbox_counts.get(f'user-{i}')}",
                )

            # 5. Verify GET /inbox?peek=1 does not mark messages delivered=1
            p_code, peek_resp = broker_req("GET", "/inbox?peek=1", key="brk-agent-1-key")
            self.assertEqual(p_code, 200)
            self.assertTrue(peek_resp["peek"])
            self.assertEqual(peek_resp["count"], 3)
            self.assertTrue(all(m["delivered"] is False for m in peek_resp["inbox"]))
            self.assertEqual(
                {m["priority"] for m in peek_resp["inbox"]},
                {"low", "high", "urgent"},
            )

            # Second peek still sees delivered=False for all 3 messages
            p2_code, peek2_resp = broker_req("GET", "/inbox?peek=1", key="brk-agent-1-key")
            self.assertEqual(p2_code, 200)
            self.assertEqual(peek2_resp["count"], 3)
            self.assertTrue(all(m["delivered"] is False for m in peek2_resp["inbox"]))

            # Consume inbox for user-1 (marks delivered=True) and verify via peek
            c_code, consume_resp = broker_req("GET", "/inbox", key="brk-agent-1-key")
            self.assertEqual(c_code, 200)
            self.assertFalse(consume_resp["peek"])
            self.assertEqual(consume_resp["count"], 3)
            self.assertTrue(all(m["delivered"] is True for m in consume_resp["inbox"]))

            after_code, after_resp = broker_req("GET", "/inbox?peek=1", key="brk-agent-1-key")
            self.assertEqual(after_code, 200)
            self.assertEqual(after_resp["count"], 3)
            self.assertTrue(all(m["delivered"] is True for m in after_resp["inbox"]))
        finally:
            if srv:
                srv.shutdown()
                srv.server_close()
            broker.Handler.log_message = orig_log
            for k in list(os.environ.keys()):
                if k.startswith("BROKER_"):
                    os.environ.pop(k, None)
            os.environ.update(saved_env)
            broker.BROKER_DB = orig_db
            broker.MAX_AGE_SEC = orig_max_age
            broker.RETENTION_SECONDS = orig_retention
            broker._min_active_ttl = orig_min_ttl
            broker._send_rl = orig_rl
            broker._load_keys()
            shutil.rmtree(tmpdir, ignore_errors=True)

    # ── Test 3: Bulk Provisioning of 1000 Users with 10 Shards ────────────

    def test_bulk_provision_1000_users_manifest(self):
        bulk_mod = _load_module("bulk_users_scale_1000", BULK_SCRIPT_PATH)
        tmp_root = pathlib.Path(tempfile.mkdtemp(prefix="ent1k_bulk_1000_"))
        try:
            # Prepare template and migrations in temporary repo root
            shutil.copytree(
                REPO_ROOT / "instances" / "_template",
                tmp_root / "instances" / "_template",
                symlinks=False,
            )
            mig_dir = tmp_root / "migrations"
            mig_dir.mkdir(parents=True, exist_ok=True)
            (mig_dir / "001_init.py").write_text("DESCRIPTION = 'init'\n", encoding="utf-8")
            (mig_dir / "024_latest.py").write_text("DESCRIPTION = 'latest'\n", encoding="utf-8")

            root_env = tmp_root / ".env"
            root_env.write_text(
                "QUOTA_ADMIN_TOKEN=" + ("adm-" * 8) + "\n",
                encoding="utf-8",
            )
            os.chmod(root_env, 0o600)

            # Generate 1,000-user manifest across 10 departments (dept-0..dept-9)
            manifest_path = tmp_root / "manifest_1000.json"
            users_manifest = [
                {
                    "name": f"user-{i}",
                    "bot_token": f"700{i:04d}:bot_{i:04d}",
                    "full_name": f"Scale User {i}",
                    "tg_id": str(10_000_000 + i),
                    "department": f"dept-{(i - 1) % 10}",
                    "quota_limit": 1_000_000,
                }
                for i in range(1, 1001)
            ]
            manifest_path.write_text(
                json.dumps({"users": users_manifest}), encoding="utf-8"
            )

            out_buf = io.StringIO()
            err_buf = io.StringIO()
            t0 = time.monotonic()
            with redirect_stdout(out_buf), redirect_stderr(err_buf):
                rc = bulk_mod.main(
                    [
                        "--root",
                        str(tmp_root),
                        "import",
                        "--file",
                        str(manifest_path),
                        "--shard-size",
                        "100",
                        "--base-port",
                        "18790",
                    ]
                )
            elapsed = time.monotonic() - t0
            self.assertEqual(rc, 0, f"bulk-users.py import failed: {err_buf.getvalue()}")
            self.assertLess(elapsed, 30.0, f"1,000-user import took too long: {elapsed:.2f}s")

            summary = json.loads(out_buf.getvalue())
            self.assertEqual(summary["created_count"], 1000)
            self.assertEqual(summary["skipped_count"], 0)

            # Verify zero port collisions across all 1,000 instances
            ports = [item["ui_port"] for item in summary["created"]]
            self.assertEqual(len(ports), 1000)
            self.assertEqual(len(set(ports)), 1000, "Detected UI port collision in 1000-user import")
            self.assertNotIn(18789, ports)
            self.assertEqual(min(ports), 18790)
            self.assertEqual(max(ports), 19789)

            # Verify 10 shards (shard-0..shard-9) each with exactly 100 instances
            shards = [item["shard"] for item in summary["created"]]
            for shard_idx in range(10):
                shard_name = f"shard-{shard_idx}"
                self.assertEqual(
                    shards.count(shard_name),
                    100,
                    f"Expected 100 instances in {shard_name}",
                )

            # Verify all 1,000 instance directories exist and root .env + override file are valid
            instances_dir = tmp_root / "instances"
            created_dirs = [
                p.name for p in instances_dir.iterdir() if p.is_dir() and p.name != "_template"
            ]
            self.assertEqual(len(created_dirs), 1000)

            for sample_name in ("user-1", "user-500", "user-1000"):
                inst_dir = instances_dir / sample_name
                self.assertTrue((inst_dir / ".env").is_file())
                self.assertTrue((inst_dir / "hermes_data" / ".env").is_file())
                self.assertTrue((inst_dir / "hermes_data" / "config.yaml").is_file())
                self.assertEqual(stat.S_IMODE((inst_dir / ".env").stat().st_mode), 0o600)

            override_text = (tmp_root / "docker-compose.override.yml").read_text(encoding="utf-8")
            for shard_idx in range(10):
                self.assertIn(f'- "shard-{shard_idx}"', override_text)
                self.assertIn(f"corp-shard-{shard_idx}:", override_text)

            # Verify status command confirms 1,000 healthy instances and 0 issues
            status_out = io.StringIO()
            with redirect_stdout(status_out), redirect_stderr(err_buf):
                rc_status = bulk_mod.main(["--root", str(tmp_root), "status"])
            self.assertEqual(rc_status, 0)
            status_data = json.loads(status_out.getvalue())
            self.assertEqual(status_data["total_instances"], 1000)
            self.assertEqual(status_data["healthy_instances"], 1000)
            self.assertEqual(status_data["degraded_instances"], 0)
            self.assertEqual(status_data["port_collisions"], {})
        finally:
            shutil.rmtree(tmp_root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
