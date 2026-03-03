#!/usr/bin/env python3
"""
CortexForge Broker — message bus  [hardened]

Hardening:
  - Constant-time key comparison
  - Rate limiting: 10 сообщений/мин на инстанс
  - Max message size: 10KB
  - Security headers
  - Message size limit in inbox
  - SQLite persistence (WAL mode) — messages survive restarts
"""

import json, os, signal, time, hashlib, hmac, threading, sqlite3
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

MAX_MSG_BYTES = 10 * 1024   # 10KB на сообщение
MAX_INBOX     = 100
MAX_AGE_SEC   = 86400
ADMIN_INSTANCE = "admin"
# Instances that can act as proxy: read/send on behalf of other instances
PROXY_INSTANCES = {"admin", "service"}

BROKER_DB = os.environ.get("BROKER_DB", "/data/broker.db")

_keys: dict[str, str] = {}   # {sha256(key): instance_name}

def _load_keys():
    keys = {}
    for k, v in os.environ.items():
        if k.startswith("BROKER_KEY_") and v:
            name = k[len("BROKER_KEY_"):].lower()
            keys[hashlib.sha256(v.strip().encode()).hexdigest()] = name
    return keys

_keys = _load_keys()


# ── SQLite storage ─────────────────────────────────────────────────────────

def _init_db():
    """Initialize SQLite database with WAL mode."""
    os.makedirs(os.path.dirname(BROKER_DB) or ".", exist_ok=True)
    conn = sqlite3.connect(BROKER_DB)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA journal_size_limit=1048576")  # 1MB
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            sender    TEXT    NOT NULL,
            recipient TEXT    NOT NULL,
            body      TEXT    NOT NULL,
            ts        REAL    NOT NULL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_messages_recipient_ts
        ON messages (recipient, ts)
    """)
    conn.commit()
    conn.close()


def _get_conn():
    """Get a SQLite connection (WAL mode set once in _init_db)."""
    conn = sqlite3.connect(BROKER_DB)
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _db_insert(sender: str, recipient: str, body: str, ts: float):
    """Insert a message and enforce MAX_INBOX per recipient."""
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO messages (sender, recipient, body, ts) VALUES (?, ?, ?, ?)",
            (sender, recipient, body, ts),
        )
        # Enforce MAX_INBOX: delete oldest messages beyond limit
        conn.execute("""
            DELETE FROM messages WHERE id IN (
                SELECT id FROM messages
                WHERE recipient = ?
                ORDER BY ts DESC
                LIMIT -1 OFFSET ?
            )
        """, (recipient, MAX_INBOX))
        conn.commit()
    finally:
        conn.close()


def _db_inbox(recipient: str) -> list[dict]:
    """Get inbox messages for a recipient (up to MAX_INBOX, excluding expired)."""
    cutoff = time.time() - MAX_AGE_SEC
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT sender, recipient, body, ts FROM messages "
            "WHERE recipient = ? AND ts > ? ORDER BY ts LIMIT ?",
            (recipient, cutoff, MAX_INBOX),
        ).fetchall()
        return [
            {"from": r[0], "to": r[1], "message": r[2], "ts": r[3]}
            for r in rows
        ]
    finally:
        conn.close()


def _db_clear(recipient: str) -> int:
    """Delete all messages for a recipient. Returns count deleted."""
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM messages WHERE recipient = ?", (recipient,))
        count = conn.execute("SELECT changes()").fetchone()[0]
        conn.commit()
        return count
    finally:
        conn.close()


def _db_counts() -> dict[str, int]:
    """Get message count per recipient."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT recipient, COUNT(*) FROM messages GROUP BY recipient"
        ).fetchall()
        return {r[0]: r[1] for r in rows}
    finally:
        conn.close()


def _cleanup():
    """Delete expired messages."""
    cutoff = time.time() - MAX_AGE_SEC
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM messages WHERE ts < ?", (cutoff,))
        conn.commit()
    finally:
        conn.close()


# ── Rate limiter ────────────────────────────────────────────────────────────
class RateLimiter:
    def __init__(self, rate: float, capacity: int):
        self.rate, self.capacity = rate, capacity
        self._b: dict[str, tuple[float, float]] = {}
        self._l = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._l:
            tokens, last = self._b.get(key, (self.capacity, now))
            tokens = min(self.capacity, tokens + (now - last) * self.rate)
            if tokens < 1:
                self._b[key] = (tokens, now); return False
            self._b[key] = (tokens - 1, now); return True

_send_rl = RateLimiter(rate=10/60, capacity=10)  # 10 сообщений в минуту

# Constant-time auth
def _auth(req) -> str | None:
    auth = req.headers.get("Authorization", "")
    if not auth.startswith("Bearer "): return None
    h = hashlib.sha256(auth[7:].encode()).hexdigest()
    result = None
    for k, name in _keys.items():
        if hmac.compare_digest(h, k):
            result = name
    return result

_SEC_HEADERS = {"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"}

class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        print(f"[broker] {self.address_string()} {fmt % args}", flush=True)

    def _json(self, code, body):
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(data))
        for k, v in _SEC_HEADERS.items(): self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/health":
            _cleanup()
            counts = _db_counts()
            self._json(200, {
                "status": "ok",
                "instances": sorted(set(_keys.values())),
                "message_counts": counts,
            })
            return

        if path == "/inbox/all":
            sender = _auth(self)
            if not sender:
                self._json(403, {"error": "Unauthorized"}); return
            if sender != ADMIN_INSTANCE:
                self._json(403, {"error": "Admin only"}); return
            _cleanup()
            counts = _db_counts()
            self._json(200, {"inboxes": counts})
            return

        if path == "/inbox":
            sender = _auth(self)
            if not sender:
                self._json(403, {"error": "Unauthorized"}); return

            target = sender
            qs = parse_qs(parsed.query)
            for_param = qs.get("for", [None])[0]
            if for_param:
                if sender not in PROXY_INSTANCES:
                    self._json(403, {"error": "Proxy access denied"}); return
                target = for_param.lower().strip()
                known = set(_keys.values())
                if target not in known:
                    self._json(404, {"error": "Unknown instance"}); return

            _cleanup()
            msgs = _db_inbox(target)
            self._json(200, {"inbox": msgs, "count": len(msgs)})
            return

        self._json(404, {"error": "Not found"})

    def do_POST(self):
        if urlparse(self.path).path != "/send":
            self._json(404, {"error": "Not found"}); return

        sender = _auth(self)
        if not sender:
            self._json(403, {"error": "Unauthorized"}); return

        # Rate limit
        if not _send_rl.allow(sender):
            self._json(429, {"error": "Rate limit exceeded (10 msg/min)"}); return

        length = int(self.headers.get("Content-Length", 0))
        if length > MAX_MSG_BYTES:
            self._json(413, {"error": f"Message too large (max {MAX_MSG_BYTES//1024}KB)"}); return

        try:
            body    = json.loads(self.rfile.read(length))
            to      = str(body.get("to", "")).lower().strip()
            message = str(body.get("message", "")).strip()
        except Exception:
            self._json(400, {"error": "Invalid JSON"}); return

        if not to or not message:
            self._json(400, {"error": "Missing 'to' or 'message'"}); return

        # Proxy: service/admin can send on behalf of another instance
        effective_sender = sender
        on_behalf_of = str(body.get("on_behalf_of", "")).lower().strip()
        if on_behalf_of:
            if sender not in PROXY_INSTANCES:
                self._json(403, {"error": "Proxy send denied"}); return
            known_names = set(_keys.values())
            if on_behalf_of not in known_names:
                self._json(404, {"error": f"Unknown sender: {on_behalf_of}"}); return
            effective_sender = on_behalf_of

        known = set(_keys.values())
        if to not in known:
            self._json(404, {"error": f"Unknown recipient: {to}"}); return
        if to == effective_sender:
            self._json(400, {"error": "Cannot send to yourself"}); return

        _cleanup()
        _db_insert(effective_sender, to, message[:MAX_MSG_BYTES], time.time())

        print(f"[broker] {effective_sender} → {to}: {message[:60]}"
              + (f" (via {sender})" if effective_sender != sender else ""),
              flush=True)
        self._json(200, {"ok": True, "from": effective_sender, "to": to})

    def do_DELETE(self):
        parsed = urlparse(self.path)
        if parsed.path != "/inbox":
            self._json(404, {"error": "Not found"}); return

        sender = _auth(self)
        if not sender:
            self._json(403, {"error": "Unauthorized"}); return

        target = sender
        qs = parse_qs(parsed.query)
        for_param = qs.get("for", [None])[0]
        if for_param:
            if sender not in PROXY_INSTANCES:
                self._json(403, {"error": "Proxy access denied"}); return
            target = for_param.lower().strip()
            known = set(_keys.values())
            if target not in known:
                self._json(404, {"error": "Unknown instance"}); return

        count = _db_clear(target)

        print(f"[broker] {target} очистил inbox ({count} сообщений)"
              + (f" (via {sender})" if target != sender else ""),
              flush=True)
        self._json(200, {"ok": True, "deleted": count})


if __name__ == "__main__":
    port = int(os.environ.get("BROKER_PORT", 8080))

    _init_db()
    print(f"[broker] SQLite DB: {BROKER_DB}", flush=True)

    if not _keys:
        print("⚠️  Нет API-ключей!", flush=True)
    else:
        print(f"✅ Broker hardened :{port} | instances: {sorted(set(_keys.values()))}", flush=True)

    server = HTTPServer(("0.0.0.0", port), Handler)

    def _shutdown(signum, frame):
        print(f"[broker] Получен сигнал {signum}, завершаем...", flush=True)
        threading.Thread(target=server.shutdown).start()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    server.serve_forever()
