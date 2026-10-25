#!/usr/bin/env python3
"""
Enterprise tests for quota-proxy (ENT1K-1: 1000-user scale readiness).

Covers:
1. SSE Anthropic streaming token accounting (message_start + message_delta)
2. SSE OpenAI streaming token accounting (usage chunk with prompt_tokens + completion_tokens)
3. Fragmented SSE chunk parsing (SSEUsageParser / _parse_sse_usage)
4. Dynamic key registration & rotation without restart (POST /quota/register-key)
5. Hot-reload of env + SQLite keys (POST /quota/reload-keys)
6. Hierarchical department quota enforcement (POST /quota/set-department-limit)
7. Report filtering (?department=, ?status=) and pagination (?limit=&offset=)
8. High-concurrency parallel requests across hundreds of users on ThreadingHTTPServer
"""

from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request


class MockUpstreamHandler(BaseHTTPRequestHandler):
    """Mock upstream supporting JSON, Anthropic SSE, and OpenAI SSE responses."""

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
        if mode == "sse_anthropic":
            in_tok = int(payload.get("in_tok", 120))
            out_tok = int(payload.get("out_tok", 45))
            events = [
                'event: message_start\n',
                f'data: {{"type":"message_start","message":{{"id":"msg_1","usage":{{"input_tokens":{in_tok},"output_tokens":1}}}}}}\n\n',
                'event: content_block_delta\n',
                'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hello"}}\n\n',
                'event: message_delta\n',
                f'data: {{"type":"message_delta","delta":{{"stop_reason":"end_turn"}},"usage":{{"output_tokens":{out_tok}}}}}\n\n',
                'event: message_stop\n',
                'data: {"type":"message_stop"}\n\n',
            ]
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.end_headers()
            for ev in events:
                self.wfile.write(ev.encode("utf-8"))
                self.wfile.flush()
            return

        if mode == "sse_openai":
            in_tok = int(payload.get("in_tok", 80))
            out_tok = int(payload.get("out_tok", 30))
            events = [
                'data: {"id":"chatcmpl-1","choices":[{"index":0,"delta":{"content":"Hi"}}]}\n\n',
                f'data: {{"id":"chatcmpl-1","choices":[],"usage":{{"prompt_tokens":{in_tok},"completion_tokens":{out_tok},"total_tokens":{in_tok + out_tok}}}}}\n\n',
                'data: [DONE]\n\n',
            ]
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for ev in events:
                self.wfile.write(ev.encode("utf-8"))
                self.wfile.flush()
            return

        in_tok = int(payload.get("in_tok", 10))
        out_tok = int(payload.get("out_tok", 20))
        body = json.dumps({
            "id": "msg_json",
            "type": "message",
            "usage": {"input_tokens": in_tok, "output_tokens": out_tok},
        }).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class TestQuotaEnterprise(unittest.TestCase):
    upstream_server = None
    proxy_server = None
    proxy_mod = None
    tmpdir = None
    db_path = None
    admin_token = "adm-test-token"

    @classmethod
    def setUpClass(cls):
        cls._saved_env = dict(os.environ)
        cls.tmpdir = tempfile.mkdtemp(prefix="quota_ent_")
        cls.db_path = os.path.join(cls.tmpdir, "quota.db")

        # Start mock upstream server first
        cls.upstream_server = ThreadingHTTPServer(("127.0.0.1", 0), MockUpstreamHandler)
        cls.upstream_port = cls.upstream_server.server_address[1]
        cls.upstream_thread = threading.Thread(
            target=cls.upstream_server.serve_forever, daemon=True
        )
        cls.upstream_thread.start()

        # Configure environment before loading quota-proxy module
        os.environ["QUOTA_DB"] = cls.db_path
        os.environ["UPSTREAM_URL"] = f"http://127.0.0.1:{cls.upstream_port}"
        os.environ["UPSTREAM_API_KEY"] = "clip-mock-upstream-key"
        os.environ["QUOTA_ADMIN_TOKEN"] = cls.admin_token
        os.environ["QUOTA_DEFAULT_MONTHLY"] = "1000000"
        os.environ["QUOTA_KEY_USER_1"] = "quota-user-1-initkey"

        proxy_path = os.path.join(
            os.path.dirname(__file__), "..", "quota-proxy", "proxy.py"
        )
        spec = importlib.util.spec_from_file_location("quota_proxy_ent", proxy_path)
        cls.proxy_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.proxy_mod)

        # Raise rate limits for high-concurrency enterprise tests
        cls.proxy_mod._admin_rl = cls.proxy_mod.RateLimiter(rate=10000.0, capacity=10000)
        cls.proxy_mod._proxy_rl = cls.proxy_mod.RateLimiter(rate=10000.0, capacity=10000)

        cls.proxy_server = ThreadingHTTPServer(("127.0.0.1", 0), cls.proxy_mod.Handler)
        cls.proxy_port = cls.proxy_server.server_address[1]
        cls.proxy_thread = threading.Thread(
            target=cls.proxy_server.serve_forever, daemon=True
        )
        cls.proxy_thread.start()

    @classmethod
    def tearDownClass(cls):
        if cls.proxy_server:
            cls.proxy_server.shutdown()
            cls.proxy_server.server_close()
        if cls.upstream_server:
            cls.upstream_server.shutdown()
            cls.upstream_server.server_close()
        if cls.proxy_mod and getattr(cls.proxy_mod, "_conn", None):
            cls.proxy_mod._conn.close()
        for suffix in ("", "-wal", "-shm"):
            p = cls.db_path + suffix
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass
        if cls.tmpdir and os.path.exists(cls.tmpdir):
            try:
                os.rmdir(cls.tmpdir)
            except OSError:
                pass
        if getattr(cls, "_saved_env", None) is not None:
            os.environ.clear()
            os.environ.update(cls._saved_env)

    def _url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.proxy_port}{path}"

    def _admin_req(self, method: str, path: str, body: dict = None) -> tuple[int, dict]:
        headers = {
            "Authorization": f"Bearer {self.admin_token}",
            "Content-Type": "application/json",
        }
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(self._url(path), data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    def _proxy_req(self, quota_key: str, payload: dict) -> tuple[int, str, bytes]:
        headers = {
            "x-api-key": quota_key,
            "Content-Type": "application/json",
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self._url("/v1/messages"), data=data, headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, r.headers.get("Content-Type", ""), r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers.get("Content-Type", ""), e.read()

    # ── 1. SSE Anthropic Streaming Accounting ────────────────────────────

    def test_01_sse_anthropic_streaming_usage_accounting(self):
        """Anthropic text/event-stream increments input & output tokens from message_start/message_delta."""
        self._admin_req("POST", "/quota/reset", {"instance": "user-1"})
        status, ct, raw = self._proxy_req(
            "quota-user-1-initkey",
            {"mock_mode": "sse_anthropic", "in_tok": 210, "out_tok": 90},
        )
        self.assertEqual(status, 200)
        self.assertIn("text/event-stream", ct)
        self.assertIn(b"event: message_start", raw)
        self.assertIn(b"event: message_delta", raw)

        usage = self.proxy_mod._get_usage("user-1")
        self.assertEqual(usage["input"], 210)
        self.assertEqual(usage["output"], 90)
        self.assertEqual(usage["total"], 300)
        self.assertEqual(usage["requests"], 1)

    # ── 2. SSE OpenAI Streaming Accounting ───────────────────────────────

    def test_02_sse_openai_streaming_usage_accounting(self):
        """OpenAI-compatible SSE stream records prompt_tokens and completion_tokens."""
        self._admin_req("POST", "/quota/reset", {"instance": "user-1"})
        status, ct, raw = self._proxy_req(
            "quota-user-1-initkey",
            {"mock_mode": "sse_openai", "in_tok": 140, "out_tok": 60},
        )
        self.assertEqual(status, 200)
        self.assertIn("text/event-stream", ct)
        self.assertIn(b"[DONE]", raw)

        usage = self.proxy_mod._get_usage("user-1")
        self.assertEqual(usage["input"], 140)
        self.assertEqual(usage["output"], 60)
        self.assertEqual(usage["total"], 200)
        self.assertEqual(usage["requests"], 1)

    # ── 3. Fragmented SSE Chunk Parser ───────────────────────────────────

    def test_03_sse_parser_fragmented_chunks(self):
        """SSEUsageParser handles arbitrary byte chunk boundaries without losing usage."""
        parser = self.proxy_mod.SSEUsageParser()
        stream = (
            b"event: message_start\r\n"
            b'data: {"type":"message_start","message":{"usage":{"input_tokens":333,"output_tokens":1}}}\r\n\r\n'
            b"event: message_delta\r\n"
            b'data: {"type":"message_delta","usage":{"output_tokens":77}}\r\n\r\n'
        )
        # Feed 7 bytes at a time to split lines across chunks
        for i in range(0, len(stream), 7):
            parser.feed_chunk(stream[i:i + 7])
        parser.finish()
        self.assertEqual(parser.input_tokens, 333)
        self.assertEqual(parser.output_tokens, 77)

    # ── 4. Dynamic Key Registration & Rotation Without Restart ───────────

    def test_04_dynamic_register_key_and_rotation(self):
        """POST /quota/register-key registers and rotates keys in SQLite + memory immediately."""
        code, resp = self._admin_req(
            "POST",
            "/quota/register-key",
            {
                "instance": "user-500",
                "quota_key": "quota-user-500-first",
                "limit": 50000,
                "department": "engineering",
            },
        )
        self.assertEqual(code, 200)
        self.assertTrue(resp["ok"])
        self.assertEqual(resp["instance"], "user-500")
        self.assertEqual(resp["department"], "engineering")
        self.assertEqual(resp["limit"], 50000)

        # Immediately usable without restart
        status, _, _ = self._proxy_req(
            "quota-user-500-first", {"mock_mode": "json", "in_tok": 25, "out_tok": 75}
        )
        self.assertEqual(status, 200)
        self.assertEqual(self.proxy_mod._get_usage("user-500")["total"], 100)

        # Rotate key for user-500: old key must be invalidated, new key must work
        code, _ = self._admin_req(
            "POST",
            "/quota/register-key",
            {
                "instance": "user-500",
                "quota_key": "quota-user-500-rotated",
                "department": "engineering",
            },
        )
        self.assertEqual(code, 200)

        # Reject invalid instance name or invalid key_hash with 400
        bad_inst_code, _ = self._admin_req(
            "POST",
            "/quota/register-key",
            {"instance": "../bad", "quota_key": "quota-bad"},
        )
        self.assertEqual(bad_inst_code, 400)
        bad_hash_code, _ = self._admin_req(
            "POST",
            "/quota/register-key",
            {"instance": "user-501", "key_hash": "not-a-sha256-hex"},
        )
        self.assertEqual(bad_hash_code, 400)

        old_status, _, _ = self._proxy_req(
            "quota-user-500-first", {"mock_mode": "json", "in_tok": 10, "out_tok": 10}
        )
        self.assertEqual(old_status, 401)

        new_status, _, _ = self._proxy_req(
            "quota-user-500-rotated", {"mock_mode": "json", "in_tok": 50, "out_tok": 50}
        )
        self.assertEqual(new_status, 200)
        self.assertEqual(self.proxy_mod._get_usage("user-500")["total"], 200)

    # ── 5. Hot-Reload Keys from Env & SQLite ─────────────────────────────

    def test_05_reload_keys_endpoint(self):
        """POST /quota/reload-keys reloads keys added to os.environ and SQLite."""
        os.environ["QUOTA_KEY_USER_777"] = "quota-user-777-hotreload"
        try:
            code, body = self._admin_req("POST", "/quota/reload-keys", {})
            self.assertEqual(code, 200)
            self.assertTrue(body["ok"])
            self.assertIn("user-777", body["instances"])
            self.assertIn("user-500", body["instances"])

            status, _, _ = self._proxy_req(
                "quota-user-777-hotreload", {"mock_mode": "json", "in_tok": 15, "out_tok": 5}
            )
            self.assertEqual(status, 200)
        finally:
            os.environ.pop("QUOTA_KEY_USER_777", None)

    # ── 6. Department Quota Enforcement ──────────────────────────────────

    def test_06_department_quota_enforcement(self):
        """Department limit blocks all instances in the department once collective usage >= limit."""
        for idx in (1, 2):
            self._admin_req(
                "POST",
                "/quota/register-key",
                {
                    "instance": f"eng-{idx}",
                    "quota_key": f"quota-eng-{idx}-key",
                    "limit": 10000,
                    "department": "ml-research",
                },
            )
            self._admin_req("POST", "/quota/reset", {"instance": f"eng-{idx}"})

        self._admin_req(
            "POST",
            "/quota/register-key",
            {
                "instance": "sales-1",
                "quota_key": "quota-sales-1-key",
                "limit": 10000,
                "department": "sales",
            },
        )
        self._admin_req("POST", "/quota/reset", {"instance": "sales-1"})

        # Set ml-research department limit to 500 tokens (while individual limits are 10,000)
        code, body = self._admin_req(
            "POST",
            "/quota/set-department-limit",
            {"department": "ml-research", "limit": 500},
        )
        self.assertEqual(code, 200)
        self.assertEqual(body["limit"], 500)

        # eng-1 uses 300 tokens -> allowed
        s1, _, _ = self._proxy_req(
            "quota-eng-1-key", {"mock_mode": "json", "in_tok": 200, "out_tok": 100}
        )
        self.assertEqual(s1, 200)

        # eng-2 uses 250 tokens -> allowed (total becomes 550 >= 500)
        s2, _, _ = self._proxy_req(
            "quota-eng-2-key", {"mock_mode": "json", "in_tok": 150, "out_tok": 100}
        )
        self.assertEqual(s2, 200)

        # Next request from eng-1 must be blocked by department limit (429)
        s3, _, raw_err = self._proxy_req(
            "quota-eng-1-key", {"mock_mode": "json", "in_tok": 10, "out_tok": 10}
        )
        self.assertEqual(s3, 429)
        err_payload = json.loads(raw_err.decode("utf-8"))
        self.assertEqual(err_payload["error"], "quota_exceeded")
        self.assertIn("департамента ml-research", err_payload["message"])

        # sales-1 in another department is unaffected
        s4, _, _ = self._proxy_req(
            "quota-sales-1-key", {"mock_mode": "json", "in_tok": 100, "out_tok": 100}
        )
        self.assertEqual(s4, 200)

    # ── 7. Report Filtering & Pagination ─────────────────────────────────

    def test_07_report_filtering_and_pagination(self):
        """GET /quota/report supports department, status, limit, offset while preserving schema."""
        # Filter by department=ml-research
        code, rep = self._admin_req("GET", "/quota/report?department=ml-research")
        self.assertEqual(code, 200)
        self.assertIn("month", rep)
        self.assertIn("usage", rep)
        self.assertIn("limits", rep)
        self.assertIn("total_instances", rep)
        self.assertIn("departments", rep)
        self.assertEqual(rep["total_instances"], 2)
        self.assertEqual(len(rep["usage"]), 2)
        for item in rep["usage"]:
            self.assertEqual(item["department"], "ml-research")
        self.assertEqual(rep["departments"]["ml-research"]["total_tokens"], 550)
        self.assertEqual(rep["departments"]["ml-research"]["status"], "❌ exceeded")

        # Pagination: limit=1&offset=0 and limit=1&offset=1
        _, page1 = self._admin_req("GET", "/quota/report?department=ml-research&limit=1&offset=0")
        _, page2 = self._admin_req("GET", "/quota/report?department=ml-research&limit=1&offset=1")
        self.assertEqual(page1["total_instances"], 2)
        self.assertEqual(len(page1["usage"]), 1)
        self.assertEqual(len(page2["usage"]), 1)
        self.assertNotEqual(page1["usage"][0]["instance"], page2["usage"][0]["instance"])

    # ── 8. High-Concurrency 250-User Parallel Stress Test ────────────────

    def test_08_high_concurrency_parallel_users(self):
        """250 distinct users registering and sending concurrent requests with zero lock failures."""
        num_users = 250

        def register_and_call(i: int):
            inst = f"corp-u-{i:04d}"
            key = f"quota-{inst}-secret-{i}"
            c1, _ = self._admin_req(
                "POST",
                "/quota/register-key",
                {
                    "instance": inst,
                    "quota_key": key,
                    "limit": 100000,
                    "department": f"dept-{i % 5}",
                },
            )
            if c1 != 200:
                return False
            c2, _, _ = self._proxy_req(
                key, {"mock_mode": "sse_anthropic", "in_tok": 10, "out_tok": 15}
            )
            return c2 == 200

        with ThreadPoolExecutor(max_workers=32) as pool:
            results = list(pool.map(register_and_call, range(num_users)))

        self.assertTrue(all(results), "All 250 concurrent user flows must succeed")

        code, rep = self._admin_req("GET", "/quota/report?limit=50&offset=0")
        self.assertEqual(code, 200)
        self.assertGreaterEqual(rep["total_instances"], num_users)
        self.assertEqual(len(rep["usage"]), 50)

    # ── 9. Concurrent Same-Instance Quota Admission Barrier ──────────────

    def test_concurrent_same_instance_quota_admission_barrier(self):
        """8 concurrent requests on the same instance with 30-token limit: 1 gets 200, 7 get 429."""
        inst = "barrier-user-1"
        key = "quota-barrier-user-1-k"
        code, _ = self._admin_req(
            "POST",
            "/quota/register-key",
            {
                "instance": inst,
                "quota_key": key,
                "limit": 30,
                "department": "barrier-dept",
            },
        )
        self.assertEqual(code, 200)
        self._admin_req("POST", "/quota/reset", {"instance": inst})

        barrier = threading.Barrier(8)

        def worker(_idx: int) -> int:
            barrier.wait(timeout=5)
            status, _, _ = self._proxy_req(
                key, {"mock_mode": "json", "in_tok": 15, "out_tok": 15}
            )
            return status

        with ThreadPoolExecutor(max_workers=8) as pool:
            statuses = list(pool.map(worker, range(8)))

        self.assertEqual(statuses.count(200), 1)
        self.assertEqual(statuses.count(429), 7)
        self.assertEqual(self.proxy_mod._get_usage(inst)["total"], 30)


if __name__ == "__main__":
    unittest.main()
