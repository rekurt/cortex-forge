#!/usr/bin/env python3
"""
Enterprise scaling tests for service-agent/server.py and resource-monitor/monitor.py
(1000-container fleet support).

Covers:
  1. service-agent:
     - MAX_CONCURRENT_SKILLS and SKILL_RATE_LIMIT env configuration
     - Per-caller rate limiting (HTTP 429 for noisy caller, other callers unaffected)
     - GET /v1/usage filtering (?caller=..., ?skill=...), pagination (?limit=..., ?offset=...),
       and by_caller / by_skill summaries
     - ThreadingHTTPServer + SQLite busy_timeout=10000
  2. resource-monitor:
     - GET /metrics on 500–1000 containers with ?search=, ?sort=mem_pct|cpu_pct|name,
       ?limit=, ?offset=, and fleet summary (total_mem_mb, avg_cpu_pct, unhealthy_count)
     - GET /alerts and GET /alerts/active with ?instance=, ?limit=, ?offset=
     - ThreadingHTTPServer + SQLite busy_timeout=10000
"""

import importlib.util
import json
import os
import shutil
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
SERVICE_SERVER_PY = ROOT_DIR / "service-agent" / "server.py"
MONITOR_SERVER_PY = ROOT_DIR / "resource-monitor" / "monitor.py"


def _http_json(method: str, url: str, body: dict | None = None, headers: dict | None = None):
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = {"raw": raw}
        return e.code, parsed


class TestServiceAgentEnterprise(unittest.TestCase):
    """Tests for service-agent enterprise scaling (rate limit, usage pagination, concurrency)."""

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix="test_svc_enterprise_")
        cls.usage_db = os.path.join(cls.tmpdir, "usage.db")
        cls.skills_dir = Path(cls.tmpdir) / "skills"
        cls.skills_dir.mkdir(parents=True, exist_ok=True)

        # Create two fast mock skills: echo-skill and calc-skill
        for skill_name in ("echo-skill", "calc-skill"):
            sdir = cls.skills_dir / skill_name
            sdir.mkdir(parents=True, exist_ok=True)
            (sdir / "skills.json").write_text(
                json.dumps({
                    "id": skill_name,
                    "name": skill_name,
                    "description": f"Test {skill_name}",
                    "runner": "run.py",
                }),
                encoding="utf-8",
            )
            (sdir / "run.py").write_text(
                "import json, sys\n"
                "data = json.loads(sys.stdin.read() or '{}')\n"
                f"print(json.dumps({{'echo': data, 'skill': '{skill_name}'}}))\n",
                encoding="utf-8",
            )

        # Set environment variables BEFORE importing service-agent/server.py
        os.environ["SERVICE_API_KEY"] = "test-enterprise-svc-key"
        os.environ["MAX_CONCURRENT_SKILLS"] = "50"
        os.environ["SKILL_RATE_LIMIT"] = "5"  # 5 req/min per caller for fast rate-limit testing
        os.environ["USAGE_DB"] = cls.usage_db
        os.environ["SKILLS_DIR"] = str(cls.skills_dir)

        spec = importlib.util.spec_from_file_location("service_agent_server", SERVICE_SERVER_PY)
        cls.svc = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.svc)

        cls.svc.init_db()
        cls.svc.reload_skills()

        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), cls.svc.ServiceHandler)
        cls.port = cls.httpd.server_address[1]
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        cls.auth_headers = {"Authorization": "Bearer test-enterprise-svc-key"}

        cls.server_thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def setUp(self):
        # Reset rate limiter and clear usage DB between tests
        self.svc._caller_limiter.reset()
        conn = sqlite3.connect(self.usage_db)
        conn.execute("DELETE FROM calls")
        conn.commit()
        conn.close()

    def test_01_health_and_config_limits(self):
        """Health endpoint exposes MAX_CONCURRENT_SKILLS=50 and SKILL_RATE_LIMIT=5."""
        status, data = _http_json("GET", f"{self.base_url}/v1/health")
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["max_concurrent"], 50)
        self.assertEqual(data["max_concurrent_skills"], 50)
        self.assertEqual(data["skill_rate_limit"], 5)

        # Verify SQLite busy_timeout is 10000 ms
        conn = self.svc._get_db_conn()
        try:
            busy_timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
            self.assertEqual(busy_timeout, 10000)
        finally:
            conn.close()

    def test_02_per_caller_rate_limiting_isolates_noisy_bot(self):
        """A runaway bot exceeding SKILL_RATE_LIMIT gets HTTP 429 while other bots succeed."""
        # user-noisy can make 5 requests (SKILL_RATE_LIMIT=5)
        for i in range(5):
            status, body = _http_json(
                "POST",
                f"{self.base_url}/v1/run",
                body={"skill": "echo-skill", "caller": "user-noisy", "params": {"seq": i}},
                headers=self.auth_headers,
            )
            self.assertEqual(status, 200, f"Request {i+1} should succeed: {body}")
            self.assertEqual(body["status"], "ok")

        # 6th request from user-noisy must be rejected with HTTP 429
        status_blocked, body_blocked = _http_json(
            "POST",
            f"{self.base_url}/v1/run",
            body={"skill": "echo-skill", "caller": "user-noisy", "params": {"seq": 99}},
            headers=self.auth_headers,
        )
        self.assertEqual(status_blocked, 429)
        self.assertEqual(body_blocked["status"], "error")
        self.assertIn("user-noisy", body_blocked.get("error", ""))

        # Meanwhile user-good-1 and user-good-2 are completely unaffected
        for good_caller in ("user-good-1", "user-good-2"):
            status_ok, body_ok = _http_json(
                "POST",
                f"{self.base_url}/v1/run",
                body={"skill": "echo-skill", "caller": good_caller, "params": {"ok": True}},
                headers=self.auth_headers,
            )
            self.assertEqual(status_ok, 200)
            self.assertEqual(body_ok["status"], "ok")

    def test_03_usage_filtering_pagination_and_by_caller_summary(self):
        """GET /v1/usage supports ?caller=, ?skill=, ?limit=, ?offset= and returns by_caller."""
        # Seed usage database directly with synthetic calls from multiple callers and skills
        call_plan = [
            ("user-001", "echo-skill", True, 20, 100),
            ("user-001", "echo-skill", True, 30, 120),
            ("user-001", "calc-skill", True, 40, 80),
            ("user-002", "echo-skill", True, 15, 90),
            ("user-002", "calc-skill", False, 50, 0),
            ("user-003", "calc-skill", True, 25, 110),
            ("user-004", "echo-skill", True, 10, 60),
        ]
        for caller, skill, ok, dur, out_len in call_plan:
            self.svc.record_call(caller, skill, {"test": 1}, ok, dur, out_len)

        # 1. Unfiltered usage stats (backward compatibility + new fields)
        status, full = _http_json("GET", f"{self.base_url}/v1/usage", headers=self.auth_headers)
        self.assertEqual(status, 200)
        self.assertIn("by_skill", full)
        self.assertIn("by_caller", full)
        self.assertEqual(full["total_calls"], 7)
        self.assertEqual(full["total_skills"], 2)
        self.assertEqual(full["total_callers"], 4)

        # Top caller should be user-001 with 3 calls
        self.assertEqual(full["by_caller"][0]["caller"], "user-001")
        self.assertEqual(full["by_caller"][0]["total_calls"], 3)
        self.assertEqual(full["by_caller"][0]["successful"], 3)

        # 2. Filter by caller (?caller=user-002)
        status, u2 = _http_json(
            "GET", f"{self.base_url}/v1/usage?caller=user-002", headers=self.auth_headers
        )
        self.assertEqual(status, 200)
        self.assertEqual(u2["total_calls"], 2)
        self.assertEqual(len(u2["by_caller"]), 1)
        self.assertEqual(u2["by_caller"][0]["caller"], "user-002")
        self.assertEqual(u2["by_caller"][0]["successful"], 1)

        # 3. Filter by skill (?skill=calc-skill)
        status, calc = _http_json(
            "GET", f"{self.base_url}/v1/usage?skill=calc-skill", headers=self.auth_headers
        )
        self.assertEqual(status, 200)
        self.assertEqual(calc["total_calls"], 3)
        self.assertEqual(len(calc["by_skill"]), 1)
        self.assertEqual(calc["by_skill"][0]["skill"], "calc-skill")
        self.assertEqual(calc["by_skill"][0]["total_calls"], 3)
        self.assertEqual(calc["by_skill"][0]["successful"], 2)

        # 4. Pagination (?limit=2&offset=1)
        status, paged = _http_json(
            "GET", f"{self.base_url}/v1/usage?limit=2&offset=1", headers=self.auth_headers
        )
        self.assertEqual(status, 200)
        self.assertEqual(len(paged["by_caller"]), 2)
        self.assertEqual(paged["by_caller"][0]["caller"], "user-002")
        self.assertEqual(len(paged["calls"]), 2)
        self.assertEqual(paged["limit"], 2)
        self.assertEqual(paged["offset"], 1)


class TestResourceMonitorEnterprise(unittest.TestCase):
    """Tests for resource-monitor enterprise scaling (500–1000 containers pagination/sorting/alerts)."""

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix="test_mon_enterprise_")
        cls.monitor_db = os.path.join(cls.tmpdir, "metrics.db")

        os.environ["MONITOR_ADMIN_TOKEN"] = "test-enterprise-mon-token"
        os.environ["MONITOR_DB"] = cls.monitor_db
        os.environ["ALERT_CPU_PCT"] = "80"
        os.environ["ALERT_RAM_PCT"] = "85"

        spec = importlib.util.spec_from_file_location("resource_monitor_server", MONITOR_SERVER_PY)
        cls.mon = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mon)

        cls.mon.init_db()

        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), cls.mon.MonitorHandler)
        cls.port = cls.httpd.server_address[1]
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        cls.auth_headers = {"Authorization": "Bearer test-enterprise-mon-token"}

        cls.server_thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def setUp(self):
        # Populate 500 containers with deterministic CPU and RAM profiles
        with self.mon._lock:
            self.mon._last_metrics.clear()
            self.mon._active_alerts.clear()
            self.mon._last_disk.update({
                "total_gb": 1000.0,
                "used_gb": 420.0,
                "free_gb": 580.0,
                "used_pct": 42.0,
            })
            for i in range(1, 501):
                name = f"corp-user-{i:04d}"
                # Make top memory consumers corp-user-0491..0500 (mem_pct > 85%)
                if i > 490:
                    ram_mb = 900.0 + (i - 490) * 10.0  # 910..1000 MB out of 1000 MB (91%..100%)
                    cpu_pct = 85.0 + (i - 490) * 1.0   # 86%..95% (> 80% threshold)
                else:
                    ram_mb = 100.0 + (i % 50) * 10.0   # 100..590 MB out of 1000 MB (10%..59%)
                    cpu_pct = round((i % 40) * 1.5, 2) # 0..58.5%

                ram_limit_mb = 1000.0
                self.mon._last_metrics[name] = {
                    "timestamp": "2026-10-25T12:00:00+00:00",
                    "id": f"cid{i:09d}",
                    "name": name,
                    "cpu_pct": cpu_pct,
                    "ram_mb": ram_mb,
                    "ram_limit_mb": ram_limit_mb,
                    "mem_pct": round(ram_mb / ram_limit_mb * 100.0, 2),
                }

    def test_01_sqlite_busy_timeout_and_batch_snapshots(self):
        """SQLite connection enforces busy_timeout=10000 and writes 500 snapshots cleanly."""
        conn = self.mon._get_db_conn()
        try:
            busy_timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
            self.assertEqual(busy_timeout, 10000)
        finally:
            conn.close()

        with self.mon._lock:
            snapshots = list(self.mon._last_metrics.values())
        self.mon.write_snapshots(snapshots)

        conn = self.mon._get_db_conn()
        try:
            count = conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
            self.assertEqual(count, 500)
        finally:
            conn.close()

    def test_02_metrics_sort_mem_pct_limit_offset_and_summary(self):
        """GET /metrics?sort=mem_pct&limit=10 returns top 10 memory containers + fleet summary."""
        status, data = _http_json(
            "GET",
            f"{self.base_url}/metrics?sort=mem_pct&limit=10&offset=0",
            headers=self.auth_headers,
        )
        self.assertEqual(status, 200)
        self.assertEqual(data["total_containers"], 500)
        self.assertEqual(len(data["containers"]), 10)

        # Verify summary fields
        summary = data["summary"]
        self.assertIn("total_mem_mb", summary)
        self.assertIn("avg_cpu_pct", summary)
        self.assertIn("unhealthy_count", summary)
        self.assertEqual(summary["unhealthy_count"], 10)  # corp-user-0491..0500 exceed CPU & RAM thresholds
        self.assertGreater(summary["total_mem_mb"], 0)
        self.assertGreater(summary["avg_cpu_pct"], 0)

        # Verify descending sort by mem_pct: corp-user-0500 (100%) down to corp-user-0491 (91%)
        mem_pcts = [c["mem_pct"] for c in data["containers"]]
        self.assertEqual(mem_pcts, sorted(mem_pcts, reverse=True))
        self.assertEqual(data["containers"][0]["name"], "corp-user-0500")
        self.assertEqual(data["containers"][0]["mem_pct"], 100.0)
        self.assertEqual(data["containers"][9]["name"], "corp-user-0491")
        self.assertEqual(data["containers"][9]["mem_pct"], 91.0)

        # Check second page (offset=5, limit=5) -> corp-user-0495..0491
        status2, page2 = _http_json(
            "GET",
            f"{self.base_url}/metrics?sort=mem_pct&limit=5&offset=5",
            headers=self.auth_headers,
        )
        self.assertEqual(status2, 200)
        self.assertEqual(page2["total_containers"], 500)
        self.assertEqual(len(page2["containers"]), 5)
        self.assertEqual(page2["containers"][0]["name"], "corp-user-0495")

    def test_03_metrics_search_and_sort_cpu_or_name(self):
        """GET /metrics supports ?search=<substr> and ?sort=cpu_pct|name."""
        # Search for "user-049" -> matches corp-user-0490..0499 (10 containers)
        status, data = _http_json(
            "GET",
            f"{self.base_url}/metrics?search=user-049&sort=cpu_pct&limit=5",
            headers=self.auth_headers,
        )
        self.assertEqual(status, 200)
        self.assertEqual(data["total_containers"], 10)
        self.assertEqual(len(data["containers"]), 5)
        self.assertEqual(data["containers"][0]["name"], "corp-user-0499")

        # Sort by name ascending
        status_name, data_name = _http_json(
            "GET",
            f"{self.base_url}/metrics?search=user-049&sort=name&limit=3",
            headers=self.auth_headers,
        )
        self.assertEqual(status_name, 200)
        names = [c["name"] for c in data_name["containers"]]
        self.assertEqual(names, ["corp-user-0490", "corp-user-0491", "corp-user-0492"])

    def test_04_alerts_and_alerts_active_filtering_and_pagination(self):
        """GET /alerts and GET /alerts/active support ?instance=, ?limit=, ?offset=."""
        # Trigger alerts via check_alerts on current 500 containers
        with self.mon._lock:
            metrics_list = list(self.mon._last_metrics.values())
            disk_dict = dict(self.mon._last_disk)
        self.mon.check_alerts(metrics_list, disk_dict, {})

        # Each of corp-user-0491..0500 triggers both cpu and ram alerts = 20 alerts total
        status, all_alerts = _http_json(
            "GET", f"{self.base_url}/alerts/active", headers=self.auth_headers
        )
        self.assertEqual(status, 200)
        self.assertEqual(all_alerts["total"], 20)
        self.assertEqual(all_alerts["count"], 20)

        # Filter by instance=corp-user-0500 (or user-0500) on /alerts
        status_inst, inst_alerts = _http_json(
            "GET",
            f"{self.base_url}/alerts?instance=user-0500",
            headers=self.auth_headers,
        )
        self.assertEqual(status_inst, 200)
        self.assertEqual(inst_alerts["total"], 2)
        self.assertEqual(inst_alerts["count"], 2)
        for alert in inst_alerts["alerts"]:
            self.assertIn("corp-user-0500", alert["key"])

        # Paginate /alerts/active?limit=5&offset=10
        status_paged, paged_alerts = _http_json(
            "GET",
            f"{self.base_url}/alerts/active?limit=5&offset=10",
            headers=self.auth_headers,
        )
        self.assertEqual(status_paged, 200)
        self.assertEqual(paged_alerts["total"], 20)
        self.assertEqual(paged_alerts["count"], 5)
        self.assertEqual(len(paged_alerts["alerts"]), 5)


if __name__ == "__main__":
    unittest.main()
