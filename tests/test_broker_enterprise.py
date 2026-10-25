#!/usr/bin/env python3
"""
Enterprise scale & feature tests for CortexForge Message Broker (ENT1K-4).

Covers:
  1. Dynamic key registration (POST /admin/register-key) & hot-reload (POST /admin/reload-keys)
  2. Underscore vs hyphen instance identity preservation (BROKER_KEY_TEAM_ONE vs BROKER_KEY_USER_1)
  3. Safe SQLite schema migration (ALTER TABLE messages ADD COLUMN priority ...)
  4. Message priorities (low, normal, high, urgent) and custom ttl_sec / TTL expiry
  5. Admin broadcast / multicast (POST /broadcast with list and "*")
  6. Inbox pagination & filtering (GET /inbox?peek=1&limit=&offset=&since_id=)
  7. Paginated GET /inbox/all (limit, offset, total_inboxes)
  8. High-concurrency workload across hundreds of agents on ThreadingHTTPServer
"""

import concurrent.futures
import json
import os
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

# Add broker directory to sys.path without mutating global env at import time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "broker"))

import broker

K_ADMIN = "adm"
K_ALICE = "alc"
K_BOB = "bob"


class TestBrokerEnterprise(unittest.TestCase):

    server = None
    server_thread = None
    port = None
    _tmpdir = None
    _test_db = None
    _orig_db = None
    _orig_rl = None
    _saved_env = None

    @classmethod
    def setUpClass(cls):
        cls._saved_env = {
            k: v for k, v in os.environ.items() if k.startswith("BROKER_")
        }
        cls._orig_db = broker.BROKER_DB
        cls._orig_rl = broker._send_rl

        cls._tmpdir = tempfile.mkdtemp()
        cls._test_db = os.path.join(cls._tmpdir, "test_broker_enterprise.db")

        broker.BROKER_DB = cls._test_db
        os.environ["BROKER_DB"] = cls._test_db
        os.environ["BROKER_KEY_ADMIN"] = K_ADMIN
        os.environ["BROKER_KEY_ALICE"] = K_ALICE
        os.environ["BROKER_KEY_BOB"] = K_BOB

        broker._init_db()
        broker._load_keys()
        broker._send_rl = broker.RateLimiter(rate=1000.0, capacity=5000)

        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), broker.Handler)
        cls.port = cls.server.server_address[1]
        cls.server_thread = threading.Thread(
            target=cls.server.serve_forever, daemon=True
        )
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        if cls.server:
            cls.server.shutdown()
            cls.server.server_close()

        # Restore environment variables so subsequent test suites remain isolated
        for k in list(os.environ.keys()):
            if k.startswith("BROKER_"):
                os.environ.pop(k, None)
        if cls._saved_env:
            os.environ.update(cls._saved_env)

        if cls._saved_env and "BROKER_DB" in cls._saved_env:
            broker.BROKER_DB = cls._saved_env["BROKER_DB"]
        elif cls._orig_db is not None:
            broker.BROKER_DB = cls._orig_db
        if cls._orig_rl is not None:
            broker._send_rl = cls._orig_rl
        broker._load_keys()

        if cls._test_db:
            for f in [cls._test_db, cls._test_db + "-wal", cls._test_db + "-shm"]:
                try:
                    os.remove(f)
                except FileNotFoundError:
                    pass
        if cls._tmpdir:
            try:
                os.rmdir(cls._tmpdir)
            except OSError:
                pass

    def setUp(self):
        broker.MAX_AGE_SEC = 86400
        broker.RETENTION_SECONDS = 86400
        broker._min_active_ttl = 86400.0
        broker._last_purge_ts = 0.0

    def _url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.port}{path}"

    def _request(self, method: str, path: str, data=None, key: str | None = None):
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        body = json.dumps(data).encode() if data is not None else None
        req = urllib.request.Request(
            self._url(path), data=body, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode())

    # ── 1. Dynamic Key Management & Hot-Reload ─────────────────────────────

    def test_register_key_and_rotate_on_the_fly(self):
        """Admin can register and rotate user-500 key without restarting broker."""
        # Non-admin cannot register keys
        code, _ = self._request(
            "POST",
            "/admin/register-key",
            {"instance": "user-500", "broker_key": "k500-v1"},
            key=K_ALICE,
        )
        self.assertEqual(code, 403)

        # Unauthenticated cannot register keys
        code, _ = self._request(
            "POST",
            "/admin/register-key",
            {"instance": "user-500", "broker_key": "k500-v1"},
        )
        self.assertEqual(code, 403)

        # Admin registers user-500
        code, body = self._request(
            "POST",
            "/admin/register-key",
            {"instance": "user-500", "broker_key": "k500-v1"},
            key=K_ADMIN,
        )
        self.assertEqual(code, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["instance"], "user-500")

        # user-500 can immediately send and receive messages
        code, send_body = self._request(
            "POST",
            "/send",
            {"to": "alice", "message": "hello from user-500"},
            key="k500-v1",
        )
        self.assertEqual(code, 200)
        self.assertEqual(send_body["from"], "user-500")

        # Rotate user-500 key to v2
        code, _ = self._request(
            "POST",
            "/admin/register-key",
            {"instance": "user-500", "broker_key": "k500-v2"},
            key=K_ADMIN,
        )
        self.assertEqual(code, 200)

        # Old key v1 is rejected
        code, _ = self._request("GET", "/inbox", key="k500-v1")
        self.assertEqual(code, 403)

        # New key v2 works immediately
        code, inbox_body = self._request("GET", "/inbox", key="k500-v2")
        self.assertEqual(code, 200)
        self.assertIn("inbox", inbox_body)

        # Reject invalid instance names ("*", "a,b", "-bad") with 400 Bad Request
        for bad_name in ("*", "a,b", "-bad", "bad space", "a" * 65):
            code, _ = self._request(
                "POST",
                "/admin/register-key",
                {"instance": bad_name, "broker_key": "k-bad"},
                key=K_ADMIN,
            )
            self.assertEqual(code, 400, f"Expected 400 for invalid instance '{bad_name}'")

    def test_rate_limiter_eviction_and_content_length_validation(self):
        """RateLimiter evicts stale buckets above 10000 entries and invalid Content-Length returns 400."""
        rl = broker.RateLimiter(rate=1.0, capacity=5)
        now = time.monotonic()
        for i in range(10005):
            rl._b[f"stale-{i}"] = (4.0, now - 200.0)
        rl._b["fresh-user"] = (4.0, now - 10.0)
        self.assertTrue(rl.allow("active-user"))
        self.assertLess(len(rl._b), 10)
        self.assertIn("fresh-user", rl._b)
        self.assertIn("active-user", rl._b)

        # Negative / malformed Content-Length returns 400
        import http.client
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.putrequest("POST", "/send")
        conn.putheader("Authorization", f"Bearer {K_ALICE}")
        conn.putheader("Content-Type", "application/json")
        conn.putheader("Content-Length", "not-an-int")
        conn.endheaders()
        resp = conn.getresponse()
        resp.read()
        conn.close()
        self.assertEqual(resp.status, 400)

    def test_reload_keys_from_env_and_sqlite(self):
        """POST /admin/reload-keys merges keys from os.environ and SQLite broker_keys."""
        os.environ["BROKER_KEY_USER_777"] = "k-777"
        try:
            code, body = self._request(
                "POST",
                "/admin/reload-keys",
                {},
                key=K_ADMIN,
            )
            self.assertEqual(code, 200)
            self.assertTrue(body["ok"])
            self.assertIn("user-777", body["instances"])

            # Verify user-777 can authenticate
            code, _ = self._request("GET", "/inbox", key="k-777")
            self.assertEqual(code, 200)
        finally:
            os.environ.pop("BROKER_KEY_USER_777", None)
            self._request("POST", "/admin/reload-keys", {}, key=K_ADMIN)

    def test_underscore_and_hyphen_env_identities_preserved(self):
        """BROKER_KEY_TEAM_ONE preserves 'team_one' identity while BROKER_KEY_USER_1 routes 'user-1'."""
        os.environ["BROKER_KEY_TEAM_ONE"] = "k-team-1"
        os.environ["BROKER_KEY_USER_1"] = "k-usr-1"
        try:
            code, body = self._request(
                "POST",
                "/admin/reload-keys",
                {},
                key=K_ADMIN,
            )
            self.assertEqual(code, 200)
            self.assertIn("team_one", body["instances"])
            self.assertIn("user-1", body["instances"])

            # 1. Send message to 'team_one' (underscore identity) and read from its inbox
            code, send_res = self._request(
                "POST",
                "/send",
                {"to": "team_one", "message": "hello team_one"},
                key=K_ALICE,
            )
            self.assertEqual(code, 200)
            self.assertEqual(send_res["to"], "team_one")

            code, team_inbox = self._request("GET", "/inbox", key="k-team-1")
            self.assertEqual(code, 200)
            self.assertTrue(
                any(m["message"] == "hello team_one" for m in team_inbox["inbox"])
            )

            # 2. Send message to 'user-1' (hyphen identity) and read from its inbox
            code, send_u1 = self._request(
                "POST",
                "/send",
                {"to": "user-1", "message": "hello user-1"},
                key=K_ALICE,
            )
            self.assertEqual(code, 200)
            self.assertEqual(send_u1["to"], "user-1")

            code, u1_inbox = self._request("GET", "/inbox", key="k-usr-1")
            self.assertEqual(code, 200)
            self.assertTrue(
                any(m["message"] == "hello user-1" for m in u1_inbox["inbox"])
            )
        finally:
            os.environ.pop("BROKER_KEY_TEAM_ONE", None)
            os.environ.pop("BROKER_KEY_USER_1", None)
            self._request("POST", "/admin/reload-keys", {}, key=K_ADMIN)

    # ── 2. Safe Migration on Legacy Schema ─────────────────────────────────

    def test_legacy_db_migration_adds_priority_column(self):
        """_init_db safely migrates an older messages table without priority column."""
        legacy_dir = tempfile.mkdtemp()
        legacy_db = os.path.join(legacy_dir, "legacy.db")
        try:
            conn = sqlite3.connect(legacy_db)
            conn.execute("""
                CREATE TABLE messages (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender    TEXT NOT NULL,
                    recipient TEXT NOT NULL,
                    body      TEXT NOT NULL,
                    ts        REAL NOT NULL
                )
            """)
            conn.execute(
                "INSERT INTO messages (sender, recipient, body, ts) VALUES ('alice', 'bob', 'legacy msg', ?)",
                (time.time(),),
            )
            conn.commit()
            conn.close()

            prev_db = broker.BROKER_DB
            broker.BROKER_DB = legacy_db
            try:
                broker._init_db()
                conn = sqlite3.connect(legacy_db)
                cols = {r[1] for r in conn.execute("PRAGMA table_info(messages)").fetchall()}
                self.assertIn("priority", cols)
                self.assertIn("delivered", cols)
                self.assertIn("created_at", cols)
                row = conn.execute("SELECT body, priority FROM messages WHERE recipient='bob'").fetchone()
                conn.close()
                self.assertEqual(row[0], "legacy msg")
                self.assertEqual(row[1], "normal")
            finally:
                broker.BROKER_DB = prev_db
                broker._load_keys()
        finally:
            for f in [legacy_db, legacy_db + "-wal", legacy_db + "-shm"]:
                try:
                    os.remove(f)
                except FileNotFoundError:
                    pass
            try:
                os.rmdir(legacy_dir)
            except OSError:
                pass

    # ── 3. Priorities & Custom TTL Expiry ──────────────────────────────────

    def test_message_priorities(self):
        """POST /send supports low, normal, high, urgent priorities and rejects invalid ones."""
        self._request("DELETE", "/inbox", key=K_BOB)

        for prio in ("low", "normal", "high", "urgent"):
            code, body = self._request(
                "POST",
                "/send",
                {"to": "bob", "message": f"prio-{prio}", "priority": prio},
                key=K_ALICE,
            )
            self.assertEqual(code, 200)
            self.assertEqual(body["priority"], prio)

        # Invalid priority returns 400
        code, _ = self._request(
            "POST",
            "/send",
            {"to": "bob", "message": "bad prio", "priority": "critical-invalid"},
            key=K_ALICE,
        )
        self.assertEqual(code, 400)

        code, inbox_body = self._request("GET", "/inbox", key=K_BOB)
        self.assertEqual(code, 200)
        priorities = [m["priority"] for m in inbox_body["inbox"] if m["message"].startswith("prio-")]
        self.assertEqual(priorities, ["low", "normal", "high", "urgent"])

    def test_ttl_expiry(self):
        """Messages expire via custom ttl_sec or short RETENTION_SECONDS without delay."""
        self._request("DELETE", "/inbox", key=K_BOB)

        # Send with custom short ttl_sec=0.3
        code, _ = self._request(
            "POST",
            "/send",
            {"to": "bob", "message": "ephemeral-ttl", "ttl_sec": 0.3},
            key=K_ALICE,
        )
        self.assertEqual(code, 200)

        # Immediately visible
        code, body = self._request("GET", "/inbox?peek=1", key=K_BOB)
        self.assertEqual(code, 200)
        self.assertTrue(any(m["message"] == "ephemeral-ttl" for m in body["inbox"]))

        # Wait for expiry
        time.sleep(0.45)

        # Should be purged & filtered out immediately
        code, body = self._request("GET", "/inbox", key=K_BOB)
        self.assertEqual(code, 200)
        self.assertFalse(any(m["message"] == "ephemeral-ttl" for m in body["inbox"]))

        # Also verify global RETENTION_SECONDS <= 5 triggers immediate purge
        broker.RETENTION_SECONDS = 1
        self._request(
            "POST",
            "/send",
            {"to": "bob", "message": "short-retention-msg"},
            key=K_ALICE,
        )
        time.sleep(1.15)
        code, body = self._request("GET", "/inbox", key=K_BOB)
        self.assertEqual(code, 200)
        self.assertFalse(any(m["message"] == "short-retention-msg" for m in body["inbox"]))

    # ── 4. Admin Broadcast / Multicast ─────────────────────────────────────

    def test_broadcast_specific_and_wildcard(self):
        """Admin can broadcast to a specific list of instances or '*' (all registered)."""
        for u in ("bcast-1", "bcast-2"):
            self._request(
                "POST",
                "/admin/register-key",
                {"instance": u, "broker_key": f"k-{u}"},
                key=K_ADMIN,
            )
            self._request("DELETE", "/inbox", key=f"k-{u}")
        self._request("DELETE", "/inbox", key=K_ALICE)

        # Non-admin cannot broadcast
        code, _ = self._request(
            "POST",
            "/broadcast",
            {"to": "*", "text": "unauthorized broadcast", "priority": "high"},
            key=K_ALICE,
        )
        self.assertEqual(code, 403)

        # Admin multicast to specific list
        code, body = self._request(
            "POST",
            "/broadcast",
            {"to": ["bcast-1", "bcast-2"], "text": "targeted maintenance", "priority": "high"},
            key=K_ADMIN,
        )
        self.assertEqual(code, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["delivered_count"], 2)

        for u in ("bcast-1", "bcast-2"):
            code, inbox = self._request("GET", "/inbox?peek=1", key=f"k-{u}")
            self.assertEqual(code, 200)
            self.assertTrue(
                any(m["message"] == "targeted maintenance" and m["priority"] == "high" for m in inbox["inbox"])
            )

        # Alice was not in the target list
        _, alice_inbox = self._request("GET", "/inbox?peek=1", key=K_ALICE)
        self.assertFalse(
            any(m["message"] == "targeted maintenance" for m in alice_inbox["inbox"])
        )

        # Admin wildcard broadcast to "*"
        code, body = self._request(
            "POST",
            "/broadcast",
            {"to": "*", "text": "global alert to all", "priority": "urgent"},
            key=K_ADMIN,
        )
        self.assertEqual(code, 200)
        self.assertGreaterEqual(body["delivered_count"], 4)

        _, alice_inbox = self._request("GET", "/inbox?peek=1", key=K_ALICE)
        self.assertTrue(
            any(m["message"] == "global alert to all" and m["priority"] == "urgent" for m in alice_inbox["inbox"])
        )

    # ── 5. Inbox Pagination, since_id, peek=1, and /inbox/all ─────────────

    def test_inbox_peek_limit_offset_since_id(self):
        """GET /inbox supports peek=1 (without marking delivered=1), limit, offset, since_id."""
        self._request("DELETE", "/inbox", key=K_BOB)

        msg_ids = []
        for i in range(6):
            code, res = self._request(
                "POST",
                "/send",
                {"to": "bob", "message": f"page-msg-{i}", "priority": "normal"},
                key=K_ALICE,
            )
            self.assertEqual(code, 200)
            msg_ids.append(res["id"])

        # 1. Peek mode: messages returned with delivered=False and DB stays delivered=0
        code, peek_body = self._request(
            "GET", "/inbox?peek=1&limit=2&offset=1", key=K_BOB
        )
        self.assertEqual(code, 200)
        self.assertEqual(peek_body["count"], 2)
        self.assertEqual([m["message"] for m in peek_body["inbox"]], ["page-msg-1", "page-msg-2"])
        self.assertTrue(all(m["delivered"] is False for m in peek_body["inbox"]))

        conn = sqlite3.connect(self._test_db)
        delivered_flags = [
            r[0] for r in conn.execute("SELECT delivered FROM messages WHERE recipient='bob'").fetchall()
        ]
        conn.close()
        self.assertEqual(delivered_flags, [0, 0, 0, 0, 0, 0])

        # 2. since_id filtering
        code, since_body = self._request(
            "GET", f"/inbox?peek=1&since_id={msg_ids[3]}", key=K_BOB
        )
        self.assertEqual(code, 200)
        self.assertEqual([m["message"] for m in since_body["inbox"]], ["page-msg-4", "page-msg-5"])

        # 3. Non-peek read marks fetched messages as delivered=1 in DB
        code, read_body = self._request(
            "GET", "/inbox?limit=3&offset=0", key=K_BOB
        )
        self.assertEqual(code, 200)
        self.assertEqual(read_body["count"], 3)
        self.assertTrue(all(m["delivered"] is True for m in read_body["inbox"]))

        conn = sqlite3.connect(self._test_db)
        delivered_after = [
            r[0]
            for r in conn.execute(
                "SELECT delivered FROM messages WHERE recipient='bob' ORDER BY id ASC"
            ).fetchall()
        ]
        conn.close()
        self.assertEqual(delivered_after, [1, 1, 1, 0, 0, 0])

    def test_inbox_all_pagination_and_total(self):
        """GET /inbox/all supports limit, offset, and returns total_inboxes."""
        self._request(
            "POST",
            "/broadcast",
            {"to": "*", "text": "populate all inboxes"},
            key=K_ADMIN,
        )

        code, full = self._request("GET", "/inbox/all", key=K_ADMIN)
        self.assertEqual(code, 200)
        total = full["total_inboxes"]
        self.assertGreaterEqual(total, 3)
        self.assertEqual(len(full["inboxes"]), total)

        code, page = self._request(
            "GET", "/inbox/all?limit=2&offset=1", key=K_ADMIN
        )
        self.assertEqual(code, 200)
        self.assertEqual(page["total_inboxes"], total)
        self.assertEqual(len(page["inboxes"]), 2)
        self.assertEqual(page["limit"], 2)
        self.assertEqual(page["offset"], 1)

    # ── 6. High-Concurrency Workload (Hundreds of Concurrent Agents) ───────

    def test_high_concurrency_agents_send_and_read(self):
        """Simulate 150 concurrent agents registering, sending, and reading in parallel."""
        num_agents = 150

        # Register 150 agents dynamically via admin endpoint
        for i in range(num_agents):
            code, _ = self._request(
                "POST",
                "/admin/register-key",
                {"instance": f"agent-{i}", "broker_key": f"ka-{i}"},
                key=K_ADMIN,
            )
            self.assertEqual(code, 200)

        def agent_worker(idx: int) -> tuple[int, int]:
            sender_key = f"ka-{idx}"
            target_idx = (idx + 1) % num_agents
            target_name = f"agent-{target_idx}"
            send_code, _ = self._request(
                "POST",
                "/send",
                {
                    "to": target_name,
                    "message": f"concurrent-payload-from-{idx}",
                    "priority": "high" if idx % 2 == 0 else "normal",
                },
                key=sender_key,
            )
            read_code, _ = self._request(
                "GET",
                "/inbox?peek=1&limit=10",
                key=sender_key,
            )
            return send_code, read_code

        with concurrent.futures.ThreadPoolExecutor(max_workers=50) as pool:
            futures = [pool.submit(agent_worker, i) for i in range(num_agents)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        for send_code, read_code in results:
            self.assertEqual(send_code, 200)
            self.assertEqual(read_code, 200)

        # Verify each of the spot-checked agents received their message without any SQLite lock errors
        spot_check_indices = [0, 17, 42, 99, 149]
        for idx in spot_check_indices:
            code, inbox_body = self._request(
                "GET", "/inbox", key=f"ka-{idx}"
            )
            self.assertEqual(code, 200)
            expected_sender = f"agent-{(idx - 1) % num_agents}"
            self.assertTrue(
                any(m["from"] == expected_sender for m in inbox_body["inbox"]),
                f"agent-{idx} missing message from {expected_sender}",
            )


if __name__ == "__main__":
    unittest.main()
