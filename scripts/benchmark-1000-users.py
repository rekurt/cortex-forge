#!/usr/bin/env python3
"""
ENT1K-3: 1000-User Concurrency & Scale Benchmark CLI for CortexForge.

Spins up an isolated temporary environment with:
  - Mock LLM Upstream (JSON + Anthropic SSE + OpenAI SSE)
  - Live quota-proxy (ThreadingHTTPServer + SQLite WAL)
  - Live message-broker (ThreadingHTTPServer + SQLite WAL)

Registers 1,000 users/agents across 10 departments (dept-0..dept-9), executes high-concurrency
workloads across a thread pool, measures throughput (RPS) and latency percentiles
(p50, p95, p99 in ms), prints a formatted benchmark table, and optionally writes
a structured JSON report via --output.

Python 3.12+ stdlib only.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import json
import math
import os
import pathlib
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
PROXY_PATH = REPO_ROOT / "quota-proxy" / "proxy.py"
BROKER_DIR = REPO_ROOT / "broker"


class HighConcurrencyHTTPServer(ThreadingHTTPServer):
    """ThreadingHTTPServer tuned for high-concurrency benchmark bursts."""

    request_queue_size = 512
    allow_reuse_address = True
    daemon_threads = True


class BenchmarkUpstreamHandler(BaseHTTPRequestHandler):
    """Fast local mock upstream supporting JSON, Anthropic SSE, and OpenAI SSE."""

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
        in_tok = int(payload.get("in_tok", 20))
        out_tok = int(payload.get("out_tok", 30))

        if mode == "sse_anthropic":
            data = (
                "event: message_start\n"
                f'data: {{"type":"message_start","message":{{"id":"msg_b","usage":{{"input_tokens":{in_tok},"output_tokens":1}}}}}}\n\n'
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
            self.wfile.write(data)
            self.wfile.flush()
            return

        if mode == "sse_openai":
            data = (
                'data: {"id":"chatcmpl-b","choices":[{"index":0,"delta":{"content":"ok"}}]}\n\n'
                f'data: {{"id":"chatcmpl-b","choices":[],"usage":{{"prompt_tokens":{in_tok},"completion_tokens":{out_tok},"total_tokens":{in_tok + out_tok}}}}}\n\n'
                "data: [DONE]\n\n"
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(data)
            self.wfile.flush()
            return

        body = json.dumps(
            {
                "id": "msg_bench",
                "type": "message",
                "usage": {"input_tokens": in_tok, "output_tokens": out_tok},
            }
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _percentile(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return round(sorted_vals[0], 2)
    rank = (pct / 100.0) * (len(sorted_vals) - 1)
    low = int(math.floor(rank))
    high = int(math.ceil(rank))
    if low == high:
        return round(sorted_vals[low], 2)
    weight = rank - low
    return round(sorted_vals[low] * (1.0 - weight) + sorted_vals[high] * weight, 2)


def _summarize_stage(
    name: str,
    latencies_ms: list[float],
    elapsed_sec: float,
    errors: int,
    logical_ops: int | None = None,
) -> dict[str, Any]:
    s = sorted(latencies_ms)
    ops = logical_ops if logical_ops is not None else len(latencies_ms)
    rps = round(ops / elapsed_sec, 1) if elapsed_sec > 0 else 0.0
    return {
        "stage": name,
        "operations": ops,
        "requests": len(latencies_ms),
        "elapsed_sec": round(elapsed_sec, 3),
        "rps": rps,
        "p50_ms": _percentile(s, 50.0),
        "p95_ms": _percentile(s, 95.0),
        "p99_ms": _percentile(s, 99.0),
        "errors": errors,
        "status": "PASS" if errors == 0 else "FAIL",
    }


@contextmanager
def _suppress_service_stdout():
    """Suppress verbose per-request service prints during benchmark execution."""
    saved_stdout = sys.stdout
    sys.stdout = io.StringIO()
    try:
        yield
    finally:
        sys.stdout = saved_stdout


def _load_module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def run_benchmark(num_users: int = 1000, workers: int = 64) -> dict[str, Any]:
    saved_env = dict(os.environ)
    tmpdir = tempfile.mkdtemp(prefix="cortex_bench_1000_")
    quota_db = os.path.join(tmpdir, "quota_bench.db")
    broker_db = os.path.join(tmpdir, "broker_bench.db")
    admin_token = "adm-bench-token-0123456789abcdef"
    broker_admin_key = "adm-broker-bench-secret"

    upstream_srv = HighConcurrencyHTTPServer(("127.0.0.1", 0), BenchmarkUpstreamHandler)
    upstream_port = upstream_srv.server_address[1]
    threading.Thread(target=upstream_srv.serve_forever, daemon=True).start()

    proxy_srv = None
    broker_srv = None
    proxy_mod = None
    broker_mod = None

    stages: list[dict[str, Any]] = []
    t_suite_start = time.monotonic()

    try:
        with _suppress_service_stdout():
            # 1. Start quota-proxy
            os.environ["QUOTA_DB"] = quota_db
            os.environ["UPSTREAM_URL"] = f"http://127.0.0.1:{upstream_port}"
            os.environ["UPSTREAM_API_KEY"] = "clip-bench-upstream-key"
            os.environ["QUOTA_ADMIN_TOKEN"] = admin_token
            os.environ["QUOTA_DEFAULT_MONTHLY"] = "1000000"

            proxy_mod = _load_module("quota_proxy_bench", PROXY_PATH)
            proxy_mod._admin_rl = proxy_mod.RateLimiter(rate=100_000.0, capacity=100_000)
            proxy_mod._proxy_rl = proxy_mod.RateLimiter(rate=100_000.0, capacity=100_000)
            proxy_mod.Handler.log_message = lambda self, fmt, *a: None

            proxy_srv = HighConcurrencyHTTPServer(("127.0.0.1", 0), proxy_mod.Handler)
            proxy_port = proxy_srv.server_address[1]
            threading.Thread(target=proxy_srv.serve_forever, daemon=True).start()

            # 2. Start message-broker
            if str(BROKER_DIR) not in sys.path:
                sys.path.insert(0, str(BROKER_DIR))
            import broker as _broker_mod

            broker_mod = _broker_mod
            broker_mod.BROKER_DB = broker_db
            broker_mod.MAX_AGE_SEC = 86400
            broker_mod.RETENTION_SECONDS = 86400
            broker_mod._min_active_ttl = 86400.0
            broker_mod._last_purge_ts = 0.0
            os.environ["BROKER_DB"] = broker_db
            os.environ["BROKER_KEY_ADMIN"] = broker_admin_key
            broker_mod._init_db()
            broker_mod._load_keys()
            broker_mod._send_rl = broker_mod.RateLimiter(rate=100_000.0, capacity=100_000)
            broker_mod.Handler.log_message = lambda self, fmt, *a: None

            broker_srv = HighConcurrencyHTTPServer(("127.0.0.1", 0), broker_mod.Handler)
            broker_port = broker_srv.server_address[1]
            threading.Thread(target=broker_srv.serve_forever, daemon=True).start()

            proxy_base = f"http://127.0.0.1:{proxy_port}"
            broker_base = f"http://127.0.0.1:{broker_port}"

            # ── Stage 1: Quota-Proxy Key Registration (1,000 users) ──────
            def qp_register(i: int) -> tuple[float, bool]:
                t0 = time.monotonic()
                payload = json.dumps(
                    {
                        "instance": f"user-{i}",
                        "quota_key": f"quota-user-{i}-bench",
                        "department": f"dept-{(i - 1) % 10}",
                        "limit": 1_000_000,
                    }
                ).encode("utf-8")
                req = urllib.request.Request(
                    f"{proxy_base}/quota/register-key",
                    data=payload,
                    headers={
                        "Authorization": f"Bearer {admin_token}",
                        "Content-Type": "application/json",
                    },
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        _ = resp.read()
                        ok = resp.status == 200
                except Exception:
                    ok = False
                return (time.monotonic() - t0) * 1000.0, ok

            t_stage = time.monotonic()
            with ThreadPoolExecutor(max_workers=workers) as pool:
                res_qp_reg = list(pool.map(qp_register, range(1, num_users + 1)))
            el_qp_reg = time.monotonic() - t_stage
            stages.append(
                _summarize_stage(
                    f"quota-proxy: Register {num_users} users",
                    [r[0] for r in res_qp_reg],
                    el_qp_reg,
                    sum(1 for r in res_qp_reg if not r[1]),
                )
            )

            # ── Stage 2: Quota-Proxy Concurrent Requests (JSON + SSE) ────
            def qp_call(i: int) -> tuple[float, bool]:
                t0 = time.monotonic()
                if i % 3 == 1:
                    mode = "json"
                elif i % 3 == 2:
                    mode = "sse_anthropic"
                else:
                    mode = "sse_openai"
                payload = json.dumps(
                    {"mock_mode": mode, "in_tok": 25, "out_tok": 25}
                ).encode("utf-8")
                req = urllib.request.Request(
                    f"{proxy_base}/v1/messages",
                    data=payload,
                    headers={
                        "x-api-key": f"quota-user-{i}-bench",
                        "Content-Type": "application/json",
                    },
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        _ = resp.read()
                        ok = resp.status == 200
                except Exception:
                    ok = False
                return (time.monotonic() - t0) * 1000.0, ok

            t_stage = time.monotonic()
            with ThreadPoolExecutor(max_workers=workers) as pool:
                res_qp_call = list(pool.map(qp_call, range(1, num_users + 1)))
            el_qp_call = time.monotonic() - t_stage
            stages.append(
                _summarize_stage(
                    f"quota-proxy: {num_users} concurrent requests (JSON+SSE)",
                    [r[0] for r in res_qp_call],
                    el_qp_call,
                    sum(1 for r in res_qp_call if not r[1]),
                )
            )

            # ── Stage 3: Quota-Proxy Paginated Report (10 pages) ─────────
            num_pages = max(1, math.ceil(num_users / 100))

            def qp_report_page(page_idx: int) -> tuple[float, bool]:
                t0 = time.monotonic()
                offset = page_idx * 100
                req = urllib.request.Request(
                    f"{proxy_base}/quota/report?limit=100&offset={offset}",
                    headers={"Authorization": f"Bearer {admin_token}"},
                    method="GET",
                )
                try:
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                        ok = resp.status == 200 and data.get("total_instances") == num_users
                except Exception:
                    ok = False
                return (time.monotonic() - t0) * 1000.0, ok

            t_stage = time.monotonic()
            with ThreadPoolExecutor(max_workers=min(workers, num_pages)) as pool:
                res_qp_rep = list(pool.map(qp_report_page, range(num_pages)))
            el_qp_rep = time.monotonic() - t_stage
            stages.append(
                _summarize_stage(
                    f"quota-proxy: Paginated report ({num_pages} pages)",
                    [r[0] for r in res_qp_rep],
                    el_qp_rep,
                    sum(1 for r in res_qp_rep if not r[1]),
                )
            )

            # ── Stage 4: Message-Broker Register 1,000 Agents ────────────
            def brk_register(i: int) -> tuple[float, bool]:
                t0 = time.monotonic()
                payload = json.dumps(
                    {"instance": f"user-{i}", "broker_key": f"brk-user-{i}-bench"}
                ).encode("utf-8")
                req = urllib.request.Request(
                    f"{broker_base}/admin/register-key",
                    data=payload,
                    headers={
                        "Authorization": f"Bearer {broker_admin_key}",
                        "Content-Type": "application/json",
                    },
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        _ = resp.read()
                        ok = resp.status == 200
                except Exception:
                    ok = False
                return (time.monotonic() - t0) * 1000.0, ok

            t_stage = time.monotonic()
            with ThreadPoolExecutor(max_workers=workers) as pool:
                res_brk_reg = list(pool.map(brk_register, range(1, num_users + 1)))
            el_brk_reg = time.monotonic() - t_stage
            stages.append(
                _summarize_stage(
                    f"message-broker: Register {num_users} agents",
                    [r[0] for r in res_brk_reg],
                    el_brk_reg,
                    sum(1 for r in res_brk_reg if not r[1]),
                )
            )

            # ── Stage 5: Message-Broker 1,000 Concurrent P2P Messages ────
            priorities = ("low", "normal", "high", "urgent")

            def brk_send(i: int) -> tuple[float, bool]:
                t0 = time.monotonic()
                target = f"user-{(i % num_users) + 1}"
                payload = json.dumps(
                    {
                        "to": target,
                        "message": f"bench-msg-{i}",
                        "priority": priorities[i % 4],
                    }
                ).encode("utf-8")
                req = urllib.request.Request(
                    f"{broker_base}/send",
                    data=payload,
                    headers={
                        "Authorization": f"Bearer brk-user-{i}-bench",
                        "Content-Type": "application/json",
                    },
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        _ = resp.read()
                        ok = resp.status == 200
                except Exception:
                    ok = False
                return (time.monotonic() - t0) * 1000.0, ok

            t_stage = time.monotonic()
            with ThreadPoolExecutor(max_workers=workers) as pool:
                res_brk_send = list(pool.map(brk_send, range(1, num_users + 1)))
            el_brk_send = time.monotonic() - t_stage
            stages.append(
                _summarize_stage(
                    f"message-broker: {num_users} concurrent P2P messages",
                    [r[0] for r in res_brk_send],
                    el_brk_send,
                    sum(1 for r in res_brk_send if not r[1]),
                )
            )

            # ── Stage 6: Message-Broker Admin Broadcast (*) to 1,000 ─────
            t_stage = time.monotonic()
            bcast_payload = json.dumps(
                {
                    "to": "*",
                    "text": "Enterprise-wide benchmark broadcast",
                    "priority": "urgent",
                }
            ).encode("utf-8")
            bcast_req = urllib.request.Request(
                f"{broker_base}/broadcast",
                data=bcast_payload,
                headers={
                    "Authorization": f"Bearer {broker_admin_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(bcast_req, timeout=15) as resp:
                    bcast_body = json.loads(resp.read().decode("utf-8"))
                    bcast_ok = (
                        resp.status == 200
                        and bcast_body.get("delivered_count") == num_users
                    )
            except Exception:
                bcast_ok = False
            el_bcast = time.monotonic() - t_stage
            stages.append(
                _summarize_stage(
                    f"message-broker: Broadcast (*) to {num_users} agents",
                    [el_bcast * 1000.0],
                    el_bcast,
                    0 if bcast_ok else 1,
                    logical_ops=num_users,
                )
            )

            # ── Stage 7: Message-Broker Paginated /inbox/all ─────────────
            def brk_inbox_page(page_idx: int) -> tuple[float, bool]:
                t0 = time.monotonic()
                offset = page_idx * 100
                req = urllib.request.Request(
                    f"{broker_base}/inbox/all?limit=100&offset={offset}",
                    headers={"Authorization": f"Bearer {broker_admin_key}"},
                    method="GET",
                )
                try:
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                        ok = resp.status == 200 and data.get("total_inboxes") == num_users
                except Exception:
                    ok = False
                return (time.monotonic() - t0) * 1000.0, ok

            t_stage = time.monotonic()
            with ThreadPoolExecutor(max_workers=min(workers, num_pages)) as pool:
                res_brk_all = list(pool.map(brk_inbox_page, range(num_pages)))
            el_brk_all = time.monotonic() - t_stage
            stages.append(
                _summarize_stage(
                    f"message-broker: Paginated /inbox/all ({num_pages} pages)",
                    [r[0] for r in res_brk_all],
                    el_brk_all,
                    sum(1 for r in res_brk_all if not r[1]),
                )
            )

        total_elapsed = round(time.monotonic() - t_suite_start, 3)
        total_ops = sum(s["operations"] for s in stages)
        total_errors = sum(s["errors"] for s in stages)
        overall_rps = round(total_ops / total_elapsed, 1) if total_elapsed > 0 else 0.0

        return {
            "benchmark": "CortexForge ENT1K-3 1000-User Scale Benchmark",
            "users": num_users,
            "workers": workers,
            "total_operations": total_ops,
            "total_elapsed_sec": total_elapsed,
            "overall_rps": overall_rps,
            "total_errors": total_errors,
            "status": "PASS" if total_errors == 0 else "FAIL",
            "stages": stages,
        }
    finally:
        if proxy_srv:
            proxy_srv.shutdown()
            proxy_srv.server_close()
        if broker_srv:
            broker_srv.shutdown()
            broker_srv.server_close()
        upstream_srv.shutdown()
        upstream_srv.server_close()
        if proxy_mod and getattr(proxy_mod, "_conn", None):
            try:
                proxy_mod._conn.close()
            except Exception:
                pass
        os.environ.clear()
        os.environ.update(saved_env)
        shutil.rmtree(tmpdir, ignore_errors=True)


def print_report_table(report: dict[str, Any]) -> None:
    title = (
        f"CortexForge 1000-User Benchmark  |  Users: {report['users']}  |  "
        f"Workers: {report['workers']}  |  Status: {report['status']}"
    )
    sep = "=" * 112
    thin = "-" * 112
    print(f"\n{sep}")
    print(f"  {title}")
    print(sep)
    header = (
        f"{'Stage':<48} | {'Ops':>6} | {'Time(s)':>7} | {'RPS':>9} | "
        f"{'p50(ms)':>8} | {'p95(ms)':>8} | {'p99(ms)':>8} | {'Err':>4}"
    )
    print(header)
    print(thin)
    for st in report["stages"]:
        print(
            f"{st['stage']:<48} | {st['operations']:>6} | {st['elapsed_sec']:>7.3f} | "
            f"{st['rps']:>9.1f} | {st['p50_ms']:>8.2f} | {st['p95_ms']:>8.2f} | "
            f"{st['p99_ms']:>8.2f} | {st['errors']:>4}"
        )
    print(thin)
    print(
        f"{'TOTAL / SUMMARY':<48} | {report['total_operations']:>6} | "
        f"{report['total_elapsed_sec']:>7.3f} | {report['overall_rps']:>9.1f} | "
        f"{'-':>8} | {'-':>8} | {'-':>8} | {report['total_errors']:>4}"
    )
    print(f"{sep}\n")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="CortexForge 1000-User Scale & Concurrency Benchmark (ENT1K-3)"
    )
    parser.add_argument(
        "--users",
        type=int,
        default=1000,
        help="Number of concurrent users/agents to benchmark (default: 1000)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=64,
        help="ThreadPoolExecutor max_workers concurrency (default: 64)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Optional path to save the JSON benchmark report",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.users < 1 or args.workers < 1:
        print("Error: --users and --workers must be >= 1", file=sys.stderr)
        return 2

    report = run_benchmark(num_users=args.users, workers=args.workers)
    print_report_table(report)

    if args.output:
        out_path = pathlib.Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"Saved JSON benchmark report to: {out_path}")

    return 0 if report["total_errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
