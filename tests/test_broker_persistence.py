#!/usr/bin/env python3
"""
Tests for broker persistence (SQLite storage).

Tests the broker HTTP API with SQLite backend, including persistence
across server restarts.
"""

import hashlib
import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
import urllib.error
from http.server import HTTPServer

# Add broker to path for importing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "broker"))

# Set up test environment before importing broker
_tmpdir = tempfile.mkdtemp()
_test_db = os.path.join(_tmpdir, "test_broker.db")
os.environ["BROKER_DB"] = _test_db
os.environ["BROKER_KEY_ALICE"] = "alice-secret-key"
os.environ["BROKER_KEY_BOB"] = "bob-secret-key"

import broker


class TestBrokerPersistence(unittest.TestCase):

    server = None
    server_thread = None
    port = None

    @classmethod
    def setUpClass(cls):
        # Reload keys with test env
        broker._keys = broker._load_keys()
        broker._init_db()
        cls.server = HTTPServer(("127.0.0.1", 0), broker.Handler)
        cls.port = cls.server.server_address[1]
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        if cls.server:
            cls.server.shutdown()
        # Clean up test DB
        for f in [_test_db, _test_db + "-wal", _test_db + "-shm"]:
            try:
                os.remove(f)
            except FileNotFoundError:
                pass
        try:
            os.rmdir(_tmpdir)
        except OSError:
            pass

    def _url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"

    def _request(self, method, path, data=None, key=None):
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(self._url(path), data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode())

    # ── Health ────────────────────────────────────────────────────────────

    def test_health(self):
        code, body = self._request("GET", "/health")
        self.assertEqual(code, 200)
        self.assertEqual(body["status"], "ok")
        self.assertIn("alice", body["instances"])
        self.assertIn("bob", body["instances"])
        self.assertIn("message_counts", body)

    # ── Auth ──────────────────────────────────────────────────────────────

    def test_inbox_no_auth(self):
        code, body = self._request("GET", "/inbox")
        self.assertEqual(code, 403)

    def test_send_no_auth(self):
        code, body = self._request("POST", "/send", {"to": "bob", "message": "hi"})
        self.assertEqual(code, 403)

    # ── Send + Inbox ──────────────────────────────────────────────────────

    def test_send_and_receive(self):
        # Alice sends to Bob
        code, body = self._request("POST", "/send",
                                   {"to": "bob", "message": "Hello Bob!"},
                                   key="alice-secret-key")
        self.assertEqual(code, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["from"], "alice")
        self.assertEqual(body["to"], "bob")

        # Bob reads inbox
        code, body = self._request("GET", "/inbox", key="bob-secret-key")
        self.assertEqual(code, 200)
        self.assertGreaterEqual(body["count"], 1)
        messages = [m for m in body["inbox"] if m["from"] == "alice" and m["message"] == "Hello Bob!"]
        self.assertGreater(len(messages), 0)

    def test_send_to_self(self):
        code, body = self._request("POST", "/send",
                                   {"to": "alice", "message": "self"},
                                   key="alice-secret-key")
        self.assertEqual(code, 400)

    def test_send_to_unknown(self):
        code, body = self._request("POST", "/send",
                                   {"to": "nonexistent", "message": "hi"},
                                   key="alice-secret-key")
        self.assertEqual(code, 404)

    def test_send_missing_fields(self):
        code, body = self._request("POST", "/send",
                                   {"to": "bob"},
                                   key="alice-secret-key")
        self.assertEqual(code, 400)

    # ── Clear ─────────────────────────────────────────────────────────────

    def test_clear_inbox(self):
        # Send a message first
        self._request("POST", "/send",
                      {"to": "alice", "message": "to be cleared"},
                      key="bob-secret-key")

        # Clear Alice's inbox
        code, body = self._request("DELETE", "/inbox", key="alice-secret-key")
        self.assertEqual(code, 200)
        self.assertTrue(body["ok"])
        self.assertGreaterEqual(body["deleted"], 1)

        # Verify inbox is empty
        code, body = self._request("GET", "/inbox", key="alice-secret-key")
        self.assertEqual(code, 200)
        self.assertEqual(body["count"], 0)

    # ── Persistence (the key test) ────────────────────────────────────────

    def test_persistence_across_db_reconnect(self):
        """Messages survive when we create a new DB connection (simulates restart)."""
        # Clear Bob's inbox first
        self._request("DELETE", "/inbox", key="bob-secret-key")

        # Send a message
        self._request("POST", "/send",
                      {"to": "bob", "message": "persistent msg"},
                      key="alice-secret-key")

        # Verify message exists via direct DB query (simulating restart)
        import sqlite3
        conn = sqlite3.connect(_test_db)
        rows = conn.execute(
            "SELECT sender, body FROM messages WHERE recipient = 'bob'"
        ).fetchall()
        conn.close()

        self.assertTrue(any(r[1] == "persistent msg" for r in rows),
                        f"Expected 'persistent msg' in DB, got: {rows}")

    # ── MAX_INBOX enforcement ─────────────────────────────────────────────

    def test_max_inbox_enforcement(self):
        """Inbox should not exceed MAX_INBOX messages."""
        # Clear first
        self._request("DELETE", "/inbox", key="bob-secret-key")

        # Send MAX_INBOX + 5 messages (using a high rate - rate limiter may kick in)
        # We directly use _db_insert to bypass rate limiting
        for i in range(broker.MAX_INBOX + 5):
            broker._db_insert("alice", "bob", f"msg {i}", time.time())

        # Check inbox count
        code, body = self._request("GET", "/inbox", key="bob-secret-key")
        self.assertEqual(code, 200)
        self.assertLessEqual(body["count"], broker.MAX_INBOX)

    # ── Health with counts ────────────────────────────────────────────────

    def test_health_message_counts(self):
        # Clear and send some messages
        self._request("DELETE", "/inbox", key="bob-secret-key")
        broker._db_insert("alice", "bob", "count test", time.time())

        code, body = self._request("GET", "/health")
        self.assertEqual(code, 200)
        self.assertIn("message_counts", body)
        self.assertIn("bob", body["message_counts"])
        self.assertGreaterEqual(body["message_counts"]["bob"], 1)

    # ── Cleanup expired ──────────────────────────────────────────────────

    def test_cleanup_expired_messages(self):
        """Expired messages should be removed by _cleanup."""
        # Insert an expired message directly
        expired_ts = time.time() - broker.MAX_AGE_SEC - 100
        broker._db_insert("alice", "bob", "expired msg", expired_ts)

        # Run cleanup
        broker._cleanup()

        # Verify expired message is gone
        import sqlite3
        conn = sqlite3.connect(_test_db)
        rows = conn.execute(
            "SELECT body FROM messages WHERE body = 'expired msg'"
        ).fetchall()
        conn.close()
        self.assertEqual(len(rows), 0)


if __name__ == "__main__":
    unittest.main()
