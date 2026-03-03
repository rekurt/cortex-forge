#!/usr/bin/env python3
"""
Tests for admin-dashboard skill (service-agent/skills/admin-dashboard/run.py).

Uses unittest with mock HTTP servers to simulate quota-proxy, monitor, and broker.
"""

import json
import os
import subprocess
import sys
import threading
import unittest
from http.server import HTTPServer, BaseHTTPRequestHandler

# Path to run.py
RUN_PY = os.path.join(
    os.path.dirname(__file__), "..", "service-agent", "skills", "admin-dashboard", "run.py"
)


class MockQuotaProxyHandler(BaseHTTPRequestHandler):
    """Mock quota-proxy."""

    def log_message(self, fmt, *args):
        pass

    def _json(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _check_admin(self):
        auth = self.headers.get("Authorization", "")
        if auth != "Bearer test-admin-token":
            self._json(403, {"error": "Unauthorized"})
            return False
        return True

    def do_GET(self):
        path = self.path.split("?")[0]

        if path == "/quota/health":
            self._json(200, {
                "status": "ok",
                "instances": ["admin", "nikita", "vasily"],
                "limits": {
                    "nikita": {"limit": 1000000, "updated_at": "2026-03-01T00:00:00Z", "updated_by": "env"},
                    "vasily": {"limit": 500000, "updated_at": "2026-03-01T00:00:00Z", "updated_by": "env"},
                },
            })
            return

        if path == "/quota/report":
            if not self._check_admin():
                return
            self._json(200, {
                "month": "2026-03",
                "usage": [
                    {
                        "instance": "nikita",
                        "month": "2026-03",
                        "input_tokens": 50000,
                        "output_tokens": 30000,
                        "total_tokens": 80000,
                        "requests": 42,
                        "limit": 1000000,
                        "used_pct": 8.0,
                        "status": "ok",
                    },
                    {
                        "instance": "vasily",
                        "month": "2026-03",
                        "input_tokens": 400000,
                        "output_tokens": 50000,
                        "total_tokens": 450000,
                        "requests": 200,
                        "limit": 500000,
                        "used_pct": 90.0,
                        "status": "warning",
                    },
                ],
                "limits": {
                    "nikita": {"limit": 1000000, "updated_at": "2026-03-01T00:00:00Z", "updated_by": "env"},
                    "vasily": {"limit": 500000, "updated_at": "2026-03-01T00:00:00Z", "updated_by": "env"},
                },
            })
            return

        self._json(404, {"error": "Not found"})

    def do_POST(self):
        path = self.path.split("?")[0]
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}

        if path == "/quota/set-limit":
            if not self._check_admin():
                return
            instance = body.get("instance", "")
            limit = body.get("limit", 0)
            self._json(200, {"ok": True, "instance": instance, "limit": limit, "current_usage": 80000})
            return

        if path == "/quota/reset":
            if not self._check_admin():
                return
            instance = body.get("instance", "")
            self._json(200, {"ok": True, "reset": instance, "month": "2026-03"})
            return

        self._json(404, {"error": "Not found"})


class MockMonitorHandler(BaseHTTPRequestHandler):
    """Mock resource-monitor."""

    def log_message(self, fmt, *args):
        pass

    def _json(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?")[0]

        if path == "/health":
            self._json(200, {"status": "ok"})
            return

        if path == "/metrics":
            self._json(200, {
                "containers": [
                    {"name": "corp-nikita", "cpu_pct": 12.5, "ram_mb": 256, "ram_limit_mb": 1024},
                    {"name": "corp-vasily", "cpu_pct": 5.2, "ram_mb": 128, "ram_limit_mb": 1024},
                    {"name": "corp-quota", "cpu_pct": 1.0, "ram_mb": 64, "ram_limit_mb": 1024},
                ],
                "disk": {"total_gb": 100, "used_gb": 45, "free_gb": 55, "used_pct": 45.0},
                "quota": {},
                "polled_at": "2026-03-01T12:00:00Z",
            })
            return

        if path == "/alerts/active":
            self._json(200, {"alerts": [], "count": 0})
            return

        self._json(404, {"error": "Not found"})


class MockBrokerHandler(BaseHTTPRequestHandler):
    """Mock broker."""

    def log_message(self, fmt, *args):
        pass

    def _json(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/health":
            self._json(200, {
                "status": "ok",
                "instances": ["admin", "nikita", "vasily", "service"],
                "message_counts": {"nikita": 2, "vasily": 0},
            })
            return
        self._json(404, {"error": "Not found"})


class TestAdminDashboard(unittest.TestCase):

    quota_server = None
    monitor_server = None
    broker_server = None
    quota_port = None
    monitor_port = None
    broker_port = None

    @classmethod
    def setUpClass(cls):
        cls.quota_server = HTTPServer(("127.0.0.1", 0), MockQuotaProxyHandler)
        cls.quota_port = cls.quota_server.server_address[1]
        threading.Thread(target=cls.quota_server.serve_forever, daemon=True).start()

        cls.monitor_server = HTTPServer(("127.0.0.1", 0), MockMonitorHandler)
        cls.monitor_port = cls.monitor_server.server_address[1]
        threading.Thread(target=cls.monitor_server.serve_forever, daemon=True).start()

        cls.broker_server = HTTPServer(("127.0.0.1", 0), MockBrokerHandler)
        cls.broker_port = cls.broker_server.server_address[1]
        threading.Thread(target=cls.broker_server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        if cls.quota_server:
            cls.quota_server.shutdown()
        if cls.monitor_server:
            cls.monitor_server.shutdown()
        if cls.broker_server:
            cls.broker_server.shutdown()

    def _run_skill(self, params, admin_token="test-admin-token"):
        env = {
            "QUOTA_PROXY_URL": f"http://127.0.0.1:{self.quota_port}",
            "QUOTA_ADMIN_TOKEN": admin_token,
            "MONITOR_URL": f"http://127.0.0.1:{self.monitor_port}",
            "BROKER_URL": f"http://127.0.0.1:{self.broker_port}",
            "PATH": os.environ.get("PATH", ""),
            "HOME": os.environ.get("HOME", ""),
        }
        proc = subprocess.run(
            [sys.executable, RUN_PY],
            input=json.dumps(params),
            capture_output=True,
            text=True,
            timeout=15,
            env=env,
        )
        if proc.returncode != 0 and not proc.stdout.strip():
            self.fail(f"run.py crashed: stderr={proc.stderr}")
        return json.loads(proc.stdout)

    # ── action: overview ──────────────────────────────────────────────────

    def test_overview_returns_all_sections(self):
        result = self._run_skill({"action": "overview"})
        self.assertEqual(result["status"], "ok")
        self.assertIn("quota", result)
        self.assertIn("metrics", result)
        self.assertIn("alerts", result)
        self.assertIn("broker", result)
        self.assertIn("summary", result)
        self.assertIn("hints", result)

    def test_overview_summary_counts(self):
        result = self._run_skill({"action": "overview"})
        summary = result["summary"]
        self.assertEqual(summary["quota_instances"], 2)
        self.assertEqual(summary["active_alerts"], 0)
        self.assertEqual(summary["broker_instances"], 4)

    def test_overview_quota_data(self):
        result = self._run_skill({"action": "overview"})
        usage = result["quota"]["usage"]
        self.assertEqual(len(usage), 2)
        nikita = next(u for u in usage if u["instance"] == "nikita")
        self.assertEqual(nikita["total_tokens"], 80000)

    # ── action: instances ─────────────────────────────────────────────────

    def test_instances_lists_all(self):
        result = self._run_skill({"action": "instances"})
        self.assertEqual(result["status"], "ok")
        self.assertIn("nikita", result["instances"])
        self.assertIn("vasily", result["instances"])
        self.assertIn("admin", result["instances"])

    def test_instances_has_usage(self):
        result = self._run_skill({"action": "instances"})
        nikita = result["instances"]["nikita"]
        self.assertIn("usage", nikita)
        self.assertEqual(nikita["usage"]["total_tokens"], 80000)

    def test_instances_has_broker(self):
        result = self._run_skill({"action": "instances"})
        nikita = result["instances"]["nikita"]
        self.assertTrue(nikita.get("broker_registered"))
        self.assertEqual(nikita.get("pending_messages"), 2)

    def test_instances_has_container_metrics(self):
        result = self._run_skill({"action": "instances"})
        nikita = result["instances"]["nikita"]
        self.assertIn("container", nikita)
        self.assertEqual(nikita["container"]["cpu_pct"], 12.5)

    # ── action: set-limit ─────────────────────────────────────────────────

    def test_set_limit_success(self):
        result = self._run_skill({"action": "set-limit", "name": "nikita", "limit": 2000000})
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["new_limit"], 2000000)
        self.assertEqual(result["instance"], "nikita")
        self.assertIn("current_usage", result)

    def test_set_limit_missing_name(self):
        result = self._run_skill({"action": "set-limit", "limit": 2000000})
        self.assertEqual(result["status"], "error")
        self.assertIn("name", result["error"].lower())

    def test_set_limit_missing_limit(self):
        result = self._run_skill({"action": "set-limit", "name": "nikita"})
        self.assertEqual(result["status"], "error")
        self.assertIn("limit", result["error"].lower())

    def test_set_limit_bad_auth(self):
        result = self._run_skill(
            {"action": "set-limit", "name": "nikita", "limit": 100},
            admin_token="wrong-token",
        )
        self.assertEqual(result["status"], "error")
        self.assertIn("auth", result["error"].lower())

    # ── action: reset-quota ───────────────────────────────────────────────

    def test_reset_quota_success(self):
        result = self._run_skill({"action": "reset-quota", "name": "nikita"})
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["instance"], "nikita")
        self.assertIn("warning", result)

    def test_reset_quota_missing_name(self):
        result = self._run_skill({"action": "reset-quota"})
        self.assertEqual(result["status"], "error")
        self.assertIn("name", result["error"].lower())

    # ── action: help ──────────────────────────────────────────────────────

    def test_help_returns_knowledge(self):
        result = self._run_skill({"action": "help"})
        self.assertEqual(result["status"], "ok")
        self.assertIn("knowledge", result)
        self.assertIn("actions", result)
        # KNOWLEDGE.md should be readable
        self.assertIn("CortexForge", result["knowledge"])

    def test_help_has_all_actions(self):
        result = self._run_skill({"action": "help"})
        actions = result["actions"]
        self.assertIn("overview", actions)
        self.assertIn("instances", actions)
        self.assertIn("set-limit", actions)
        self.assertIn("reset-quota", actions)
        self.assertIn("help", actions)

    # ── error handling ────────────────────────────────────────────────────

    def test_missing_action(self):
        result = self._run_skill({})
        self.assertEqual(result["status"], "error")
        self.assertIn("action", result["error"].lower())

    def test_unknown_action(self):
        result = self._run_skill({"action": "unknown"})
        self.assertEqual(result["status"], "error")
        self.assertIn("unknown", result["error"].lower())

    def test_no_admin_token_for_admin_action(self):
        result = self._run_skill({"action": "overview"}, admin_token="")
        self.assertEqual(result["status"], "error")
        self.assertIn("QUOTA_ADMIN_TOKEN", result["error"])

    def test_help_works_without_admin_token(self):
        """Help action should work even without QUOTA_ADMIN_TOKEN."""
        env = {
            "QUOTA_PROXY_URL": f"http://127.0.0.1:{self.quota_port}",
            "QUOTA_ADMIN_TOKEN": "",
            "MONITOR_URL": f"http://127.0.0.1:{self.monitor_port}",
            "BROKER_URL": f"http://127.0.0.1:{self.broker_port}",
            "PATH": os.environ.get("PATH", ""),
            "HOME": os.environ.get("HOME", ""),
        }
        proc = subprocess.run(
            [sys.executable, RUN_PY],
            input=json.dumps({"action": "help"}),
            capture_output=True,
            text=True,
            timeout=15,
            env=env,
        )
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "ok")


if __name__ == "__main__":
    unittest.main()
