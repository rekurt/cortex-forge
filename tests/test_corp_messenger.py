#!/usr/bin/env python3
"""
Tests for corp-messenger skill (service-agent/skills/corp-messenger/run.py).

Uses unittest with mock HTTP server to simulate broker responses.
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
    os.path.dirname(__file__), "..", "service-agent", "skills", "corp-messenger", "run.py"
)

# Find a free port for mock broker
MOCK_PORT = 0  # will be assigned by OS


class MockBrokerHandler(BaseHTTPRequestHandler):
    """Mock broker that simulates all broker API endpoints."""

    # Class-level response overrides for testing error scenarios
    custom_response = None

    def log_message(self, fmt, *args):
        pass  # suppress logs during tests

    def _json(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _check_auth(self):
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or auth[7:] != "test-broker-key":
            self._json(403, {"error": "Unauthorized"})
            return False
        return True

    def do_GET(self):
        if MockBrokerHandler.custom_response:
            code, body = MockBrokerHandler.custom_response
            self._json(code, body)
            return

        if self.path == "/health":
            self._json(200, {"status": "ok", "instances": ["admin", "user-1", "user-4"]})
            return

        if self.path == "/inbox":
            if not self._check_auth():
                return
            self._json(200, {
                "inbox": [
                    {"from": "user-1", "to": "service", "message": "Hello!", "ts": 1709312400.0}
                ],
                "count": 1,
            })
            return

        self._json(404, {"error": "Not found"})

    def do_POST(self):
        if MockBrokerHandler.custom_response:
            code, body = MockBrokerHandler.custom_response
            self._json(code, body)
            return

        if self.path == "/send":
            if not self._check_auth():
                return
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            to = body.get("to", "")
            if to not in ("admin", "user-1", "user-4"):
                self._json(404, {"error": f"Unknown recipient: {to}"})
                return
            self._json(200, {"ok": True, "from": "service", "to": to})
            return

        self._json(404, {"error": "Not found"})

    def do_DELETE(self):
        if MockBrokerHandler.custom_response:
            code, body = MockBrokerHandler.custom_response
            self._json(code, body)
            return

        if self.path == "/inbox":
            if not self._check_auth():
                return
            self._json(200, {"ok": True, "deleted": 3})
            return

        self._json(404, {"error": "Not found"})


class TestCorpMessenger(unittest.TestCase):

    server = None
    server_thread = None
    port = None

    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), MockBrokerHandler)
        cls.port = cls.server.server_address[1]
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        if cls.server:
            cls.server.shutdown()

    def setUp(self):
        MockBrokerHandler.custom_response = None

    def _run_skill(self, params, broker_key="test-broker-key"):
        env = {
            "BROKER_URL": f"http://127.0.0.1:{self.port}",
            "BROKER_KEY": broker_key,
            "PATH": os.environ.get("PATH", ""),
            "HOME": os.environ.get("HOME", ""),
        }
        proc = subprocess.run(
            [sys.executable, RUN_PY],
            input=json.dumps(params),
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )
        if proc.returncode != 0 and not proc.stdout.strip():
            self.fail(f"run.py crashed: stderr={proc.stderr}")
        return json.loads(proc.stdout)

    # ── action: list ──────────────────────────────────────────────────────

    def test_list_instances(self):
        result = self._run_skill({"action": "list"})
        self.assertEqual(result["status"], "ok")
        self.assertIn("admin", result["instances"])
        self.assertIn("user-1", result["instances"])
        self.assertEqual(result["count"], 3)

    # ── action: send ──────────────────────────────────────────────────────

    def test_send_success(self):
        result = self._run_skill({"action": "send", "to": "user-1", "message": "Hello!"})
        self.assertEqual(result["status"], "ok")
        self.assertIn("user-1", result["message"])

    def test_send_missing_to(self):
        result = self._run_skill({"action": "send", "message": "Hello!"})
        self.assertEqual(result["status"], "error")
        self.assertIn("to", result["error"].lower())

    def test_send_missing_message(self):
        result = self._run_skill({"action": "send", "to": "user-1"})
        self.assertEqual(result["status"], "error")
        self.assertIn("message", result["error"].lower())

    def test_send_unknown_recipient(self):
        result = self._run_skill({"action": "send", "to": "unknown_user", "message": "Hi"})
        self.assertEqual(result["status"], "error")
        self.assertIn("unknown", result["error"].lower())

    def test_send_bad_auth(self):
        result = self._run_skill(
            {"action": "send", "to": "user-1", "message": "Hi"},
            broker_key="wrong-key",
        )
        self.assertEqual(result["status"], "error")
        self.assertIn("auth", result["error"].lower())

    # ── action: inbox ─────────────────────────────────────────────────────

    def test_inbox_success(self):
        result = self._run_skill({"action": "inbox"})
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["count"], 1)
        self.assertEqual(len(result["inbox"]), 1)
        self.assertEqual(result["inbox"][0]["from"], "user-1")

    def test_inbox_bad_auth(self):
        result = self._run_skill({"action": "inbox"}, broker_key="wrong-key")
        self.assertEqual(result["status"], "error")

    # ── action: clear ─────────────────────────────────────────────────────

    def test_clear_success(self):
        result = self._run_skill({"action": "clear"})
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["deleted"], 3)

    # ── error handling ────────────────────────────────────────────────────

    def test_missing_action(self):
        result = self._run_skill({})
        self.assertEqual(result["status"], "error")
        self.assertIn("action", result["error"].lower())

    def test_unknown_action(self):
        result = self._run_skill({"action": "unknown"})
        self.assertEqual(result["status"], "error")
        self.assertIn("unknown", result["error"].lower())

    def test_rate_limit_response(self):
        MockBrokerHandler.custom_response = (429, {"error": "Rate limit exceeded (10 msg/min)"})
        result = self._run_skill({"action": "send", "to": "user-1", "message": "Hi"})
        self.assertEqual(result["status"], "error")
        self.assertIn("rate limit", result["error"].lower())

    def test_no_broker_key_for_authed_action(self):
        result = self._run_skill({"action": "inbox"}, broker_key="")
        self.assertEqual(result["status"], "error")
        self.assertIn("BROKER_KEY", result["error"])


if __name__ == "__main__":
    unittest.main()
