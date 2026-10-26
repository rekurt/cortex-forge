#!/usr/bin/env python3
"""
CortexForge Broker — Enterprise message bus  [hardened, 1000-agent scale]

Hardening & Enterprise capabilities:
  - Constant-time key comparison (hmac.compare_digest)
  - Thread-safe dynamic key management (SQLite broker_keys + env hot-reload)
  - Per-instance rate limiting
  - Max message size: 10KB
  - Message priorities (low, normal, high, urgent) & custom per-message TTL
  - Admin broadcast / multicast endpoint (/broadcast)
  - Paginated & filtered inbox (/inbox with limit, offset, since_id, peek; /inbox/all)
  - High-concurrency SQLite (WAL mode, synchronous=NORMAL, busy_timeout=10000,
    composite indexes, throttled batch purge, ThreadingHTTPServer)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import signal
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

MAX_MSG_BYTES = 10 * 1024   # 10KB на сообщение
MAX_INBOX = int(os.environ.get("MAX_INBOX", 100))
MAX_AGE_SEC = int(os.environ.get("RETENTION_SECONDS", os.environ.get("MAX_AGE_SEC", 86400)))
RETENTION_SECONDS = MAX_AGE_SEC
PURGE_INTERVAL_SEC = float(os.environ.get("BROKER_PURGE_INTERVAL_SEC", 5.0))

ADMIN_INSTANCE = "admin"
# Instances that can act as proxy: read/send on behalf of other instances
PROXY_INSTANCES = {"admin", "service"}
VALID_PRIORITIES = {"low", "normal", "high", "urgent"}
_INSTANCE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

BROKER_DB = os.environ.get("BROKER_DB", "/data/broker.db")

_keys_lock = threading.RLock()
_db_write_lock = threading.RLock()
_purge_lock = threading.Lock()
_last_purge_ts: float = 0.0
_min_active_ttl: float = float(MAX_AGE_SEC)

_keys: dict[str, str] = {}              # {sha256(key): canonical_instance_name}
_instance_aliases: dict[str, str] = {}  # {alias_or_name: canonical_instance_name}
_REPO_INSTANCES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "instances"
)


def _retention_sec() -> float:
    """Return active retention window in seconds, respecting runtime test overrides."""
    if RETENTION_SECONDS != 86400:
        return float(RETENTION_SECONDS)
    return float(MAX_AGE_SEC)


def _active_db_path() -> str:
    """Resolve active SQLite database path, honoring runtime BROKER_DB overrides."""
    global BROKER_DB
    env_db = os.environ.get("BROKER_DB")
    if BROKER_DB == "/data/broker.db" and env_db:
        BROKER_DB = env_db
    return BROKER_DB


def _get_conn() -> sqlite3.Connection:
    """Get a SQLite connection configured for high concurrency."""
    conn = sqlite3.connect(_active_db_path(), timeout=10.0)
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _resolve_env_instance_name(suffix: str) -> tuple[str, str, str]:
    """Return (canonical_name, raw_name, hyphen_name) for a BROKER_KEY_<SUFFIX> variable."""
    raw_name = suffix.lower().strip()
    hyphen_name = raw_name.replace("_", "-")
    explicit = os.environ.get(f"BROKER_INSTANCE_{suffix}", "").lower().strip()
    if explicit:
        return explicit, raw_name, hyphen_name

    if hyphen_name != raw_name:
        for base_dir in ("instances", _REPO_INSTANCES_DIR):
            hyphen_dir = os.path.join(base_dir, hyphen_name)
            raw_dir = os.path.join(base_dir, raw_name)
            if os.path.isdir(hyphen_dir) and not os.path.isdir(raw_dir):
                return hyphen_name, raw_name, hyphen_name

    return raw_name, raw_name, hyphen_name


def _load_keys() -> dict[str, str]:
    """Load and merge broker keys from environment (BROKER_KEY_*) and SQLite (broker_keys)."""
    keys: dict[str, str] = {}
    aliases: dict[str, str] = {}

    for k, v in os.environ.items():
        if k.startswith("BROKER_KEY_") and v:
            suffix = k[len("BROKER_KEY_"):]
            canonical, raw_name, hyphen_name = _resolve_env_instance_name(suffix)
            if canonical:
                keys[hashlib.sha256(v.strip().encode()).hexdigest()] = canonical
                aliases[canonical] = canonical
                aliases[raw_name] = canonical
                aliases[hyphen_name] = canonical

    db_path = _active_db_path()
    if db_path and os.path.exists(db_path):
        try:
            conn = _get_conn()
            try:
                rows = conn.execute(
                    "SELECT instance, key_hash FROM broker_keys"
                ).fetchall()
                for inst, key_hash in rows:
                    inst_norm = str(inst).lower().strip()
                    if not inst_norm or not key_hash:
                        continue
                    for old_h, old_inst in list(keys.items()):
                        if old_inst == inst_norm:
                            del keys[old_h]
                    keys[str(key_hash)] = inst_norm
                    aliases[inst_norm] = inst_norm
                    alt_hyphen = inst_norm.replace("_", "-")
                    alt_raw = inst_norm.replace("-", "_")
                    aliases.setdefault(alt_hyphen, inst_norm)
                    aliases.setdefault(alt_raw, inst_norm)
            finally:
                conn.close()
        except sqlite3.Error:
            pass

    with _keys_lock:
        _keys.clear()
        _keys.update(keys)
        _instance_aliases.clear()
        _instance_aliases.update(aliases)
        return _keys


_keys = _load_keys()


def _known_instances() -> set[str]:
    """Return thread-safe snapshot of canonical registered instance names."""
    with _keys_lock:
        return set(_keys.values())


def _known_with_aliases() -> set[str]:
    """Return all canonical instance names and registered underscore/hyphen aliases."""
    with _keys_lock:
        canonical = set(_keys.values())
        return canonical | {
            alias for alias, target in _instance_aliases.items() if target in canonical
        }


def _resolve_instance(name: str) -> str | None:
    """Resolve an instance name or its underscore/hyphen alias to its canonical identity."""
    norm = name.lower().strip()
    if not norm:
        return None
    with _keys_lock:
        canonical_set = set(_keys.values())
        if norm in canonical_set:
            return norm
        mapped = _instance_aliases.get(norm)
        if mapped and mapped in canonical_set:
            return mapped
        # Fallback if _keys was mutated directly in tests without updating _instance_aliases
        alt_underscore = norm.replace("-", "_")
        if alt_underscore in canonical_set:
            return alt_underscore
        alt_hyphen = norm.replace("_", "-")
        if alt_hyphen in canonical_set:
            return alt_hyphen
    return None


def _register_key(instance: str, broker_key: str) -> str:
    """Register or update an instance's broker key in SQLite and in-memory map."""
    inst_norm = instance.lower().strip()
    key_hash = hashlib.sha256(broker_key.strip().encode()).hexdigest()
    now_ts = int(time.time())

    with _db_write_lock:
        conn = _get_conn()
        try:
            conn.execute(
                """
                INSERT INTO broker_keys (instance, key_hash, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(instance) DO UPDATE SET
                    key_hash = excluded.key_hash,
                    updated_at = excluded.updated_at
                """,
                (inst_norm, key_hash, now_ts),
            )
            conn.commit()
        finally:
            conn.close()

    with _keys_lock:
        for old_h, old_inst in list(_keys.items()):
            if old_inst == inst_norm:
                del _keys[old_h]
        _keys[key_hash] = inst_norm
        _instance_aliases[inst_norm] = inst_norm
        _instance_aliases.setdefault(inst_norm.replace("_", "-"), inst_norm)
        _instance_aliases.setdefault(inst_norm.replace("-", "_"), inst_norm)

    return key_hash


# ── SQLite storage ─────────────────────────────────────────────────────────

def _init_db():
    """Initialize SQLite database with WAL mode, migrations, and enterprise indexes."""
    db_path = _active_db_path()
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    with _db_write_lock:
        conn = sqlite3.connect(db_path, timeout=10.0)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=10000")
            conn.execute("PRAGMA journal_size_limit=1048576")  # 1MB
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender     TEXT    NOT NULL,
                    recipient  TEXT    NOT NULL,
                    body       TEXT    NOT NULL,
                    ts         REAL    NOT NULL,
                    priority   TEXT    DEFAULT 'normal',
                    delivered  INTEGER DEFAULT 0,
                    created_at REAL    DEFAULT 0,
                    expires_at REAL    DEFAULT NULL
                )
            """)

            # Safe migrations for pre-existing databases
            existing_cols = {
                r[1] for r in conn.execute("PRAGMA table_info(messages)").fetchall()
            }
            if "priority" not in existing_cols:
                conn.execute("ALTER TABLE messages ADD COLUMN priority TEXT DEFAULT 'normal'")
            if "delivered" not in existing_cols:
                conn.execute("ALTER TABLE messages ADD COLUMN delivered INTEGER DEFAULT 0")
            if "created_at" not in existing_cols:
                conn.execute("ALTER TABLE messages ADD COLUMN created_at REAL DEFAULT 0")
                conn.execute("UPDATE messages SET created_at = ts WHERE created_at = 0 OR created_at IS NULL")
            if "expires_at" not in existing_cols:
                conn.execute("ALTER TABLE messages ADD COLUMN expires_at REAL DEFAULT NULL")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS broker_keys (
                    instance   TEXT PRIMARY KEY,
                    key_hash   TEXT NOT NULL,
                    updated_at INTEGER
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_recipient_ts
                ON messages (recipient, ts)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_recipient_delivered_created
                ON messages (recipient, delivered, created_at)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_expires_at
                ON messages (expires_at)
            """)
            conn.commit()
        finally:
            conn.close()

    _load_keys()


def _db_insert(
    sender: str,
    recipient: str,
    body: str,
    ts: float,
    priority: str = "normal",
    ttl_sec: float | None = None,
) -> int:
    """Insert a message and enforce MAX_INBOX per recipient."""
    global _min_active_ttl
    prio = priority if priority in VALID_PRIORITIES else "normal"
    retention = _retention_sec()
    expires_at = None
    if ttl_sec is not None:
        effective_ttl = max(0.001, min(float(ttl_sec), retention))
        expires_at = ts + effective_ttl
        if effective_ttl <= 5.0:
            _min_active_ttl = min(_min_active_ttl, effective_ttl)

    with _db_write_lock:
        conn = _get_conn()
        try:
            cur = conn.execute(
                """
                INSERT INTO messages (sender, recipient, body, ts, priority, delivered, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, 0, ?, ?)
                """,
                (sender, recipient, body, ts, prio, ts, expires_at),
            )
            msg_id = int(cur.lastrowid or 0)
            # Enforce MAX_INBOX: delete oldest messages beyond limit
            conn.execute(
                """
                DELETE FROM messages WHERE id IN (
                    SELECT id FROM messages
                    WHERE recipient = ?
                    ORDER BY ts DESC, id DESC
                    LIMIT -1 OFFSET ?
                )
                """,
                (recipient, MAX_INBOX),
            )
            conn.commit()
            return msg_id
        finally:
            conn.close()


def _db_broadcast(
    sender: str,
    recipients: list[str],
    body: str,
    ts: float,
    priority: str = "normal",
    ttl_sec: float | None = None,
) -> int:
    """Insert broadcast message to multiple recipients in a single SQLite transaction."""
    global _min_active_ttl
    if not recipients:
        return 0
    prio = priority if priority in VALID_PRIORITIES else "normal"
    retention = _retention_sec()
    expires_at = None
    if ttl_sec is not None:
        effective_ttl = max(0.001, min(float(ttl_sec), retention))
        expires_at = ts + effective_ttl
        if effective_ttl <= 5.0:
            _min_active_ttl = min(_min_active_ttl, effective_ttl)

    with _db_write_lock:
        conn = _get_conn()
        try:
            conn.executemany(
                """
                INSERT INTO messages (sender, recipient, body, ts, priority, delivered, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, 0, ?, ?)
                """,
                [(sender, r, body, ts, prio, ts, expires_at) for r in recipients],
            )
            for r in recipients:
                conn.execute(
                    """
                    DELETE FROM messages WHERE id IN (
                        SELECT id FROM messages
                        WHERE recipient = ?
                        ORDER BY ts DESC, id DESC
                        LIMIT -1 OFFSET ?
                    )
                    """,
                    (r, MAX_INBOX),
                )
            conn.commit()
            return len(recipients)
        finally:
            conn.close()


def _db_inbox(
    recipient: str,
    limit: int | None = None,
    offset: int = 0,
    since_id: int | None = None,
    peek: bool = False,
) -> list[dict]:
    """Get inbox messages for a recipient with optional pagination, since_id, and peek mode."""
    now = time.time()
    cutoff = now - _retention_sec()
    eff_limit = MAX_INBOX if limit is None else max(0, min(int(limit), MAX_INBOX))
    eff_offset = max(0, int(offset))

    query = (
        "SELECT id, sender, recipient, body, ts, priority, delivered "
        "FROM messages "
        "WHERE recipient = ? AND ts > ? AND (expires_at IS NULL OR expires_at > ?)"
    )
    params: list = [recipient, cutoff, now]

    if since_id is not None:
        query += " AND id > ?"
        params.append(int(since_id))

    query += " ORDER BY ts ASC, id ASC LIMIT ? OFFSET ?"
    params.extend([eff_limit, eff_offset])

    if peek:
        conn = _get_conn()
        try:
            rows = conn.execute(query, tuple(params)).fetchall()
        finally:
            conn.close()
        return [
            {
                "id": r[0],
                "from": r[1],
                "to": r[2],
                "message": r[3],
                "ts": r[4],
                "priority": r[5] or "normal",
                "delivered": bool(r[6]),
            }
            for r in rows
        ]

    with _db_write_lock:
        conn = _get_conn()
        try:
            rows = conn.execute(query, tuple(params)).fetchall()
            undelivered_ids = [r[0] for r in rows if not r[6]]
            if undelivered_ids:
                placeholders = ",".join("?" for _ in undelivered_ids)
                conn.execute(
                    f"UPDATE messages SET delivered = 1 WHERE id IN ({placeholders})",
                    tuple(undelivered_ids),
                )
                conn.commit()
        finally:
            conn.close()

    return [
        {
            "id": r[0],
            "from": r[1],
            "to": r[2],
            "message": r[3],
            "ts": r[4],
            "priority": r[5] or "normal",
            "delivered": True,
        }
        for r in rows
    ]


def _db_clear(recipient: str) -> tuple[int, int]:
    """Delete all messages for a recipient. Returns (deleted, remaining)."""
    with _db_write_lock:
        conn = _get_conn()
        try:
            conn.execute("DELETE FROM messages WHERE recipient = ?", (recipient,))
            count = conn.execute("SELECT changes()").fetchone()[0]
            conn.commit()
            remaining = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE recipient = ?", (recipient,)
            ).fetchone()[0]
            return count, remaining
        finally:
            conn.close()


def _db_counts() -> dict[str, int]:
    """Get active message count per recipient."""
    now = time.time()
    cutoff = now - _retention_sec()
    conn = _get_conn()
    try:
        rows = conn.execute(
            """
            SELECT recipient, COUNT(*) FROM messages
            WHERE ts > ? AND (expires_at IS NULL OR expires_at > ?)
            GROUP BY recipient
            """,
            (cutoff, now),
        ).fetchall()
        return {r[0]: r[1] for r in rows}
    finally:
        conn.close()


def _purge_expired(force: bool = False) -> int:
    """Batch-delete expired messages, throttled unless force=True or short TTL is active."""
    global _last_purge_ts
    now = time.time()
    retention = _retention_sec()
    immediate = force or (retention <= 5.0) or (_min_active_ttl <= 5.0)

    if not immediate and (now - _last_purge_ts) < PURGE_INTERVAL_SEC:
        return 0

    if not _purge_lock.acquire(blocking=immediate):
        return 0

    try:
        now = time.time()
        if not immediate and (now - _last_purge_ts) < PURGE_INTERVAL_SEC:
            return 0
        cutoff = now - retention
        with _db_write_lock:
            conn = _get_conn()
            try:
                conn.execute(
                    "DELETE FROM messages WHERE ts < ? OR (expires_at IS NOT NULL AND expires_at <= ?)",
                    (cutoff, now),
                )
                deleted = conn.execute("SELECT changes()").fetchone()[0]
                conn.commit()
                _last_purge_ts = now
                return deleted
            finally:
                conn.close()
    finally:
        _purge_lock.release()


def _cleanup():
    """Immediately delete expired messages (backward-compatible entrypoint)."""
    return _purge_expired(force=True)


# ── Rate limiter ────────────────────────────────────────────────────────────
class RateLimiter:
    def __init__(self, rate: float, capacity: int):
        self.rate, self.capacity = rate, capacity
        self._b: dict[str, tuple[float, float]] = {}
        self._l = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._l:
            if len(self._b) > 10000:
                self._b = {k: v for k, v in self._b.items() if now - v[1] <= 120}
            tokens, last = self._b.get(key, (self.capacity, now))
            tokens = min(self.capacity, tokens + (now - last) * self.rate)
            if tokens < 1:
                self._b[key] = (tokens, now)
                return False
            self._b[key] = (tokens - 1, now)
            return True


RATE_LIMIT_PER_MIN = float(os.environ.get("BROKER_RATE_LIMIT_PER_MIN", 10))
RATE_LIMIT_BURST = int(os.environ.get("BROKER_RATE_LIMIT_BURST", 10))
_send_rl = RateLimiter(rate=RATE_LIMIT_PER_MIN / 60.0, capacity=RATE_LIMIT_BURST)


# Constant-time auth
def _auth(req) -> str | None:
    auth = req.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    h = hashlib.sha256(auth[7:].encode()).hexdigest()
    result = None
    with _keys_lock:
        items = list(_keys.items())
    for k, name in items:
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
        for k, v in _SEC_HEADERS.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _parse_content_length(self) -> int | None:
        raw_len = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_len)
        except (TypeError, ValueError):
            self._json(400, {"error": "Invalid Content-Length"})
            return None
        if length < 0:
            self._json(400, {"error": "Invalid Content-Length"})
            return None
        return length

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/health":
            _purge_expired()
            counts = _db_counts()
            self._json(200, {
                "status": "ok",
                "instances": sorted(_known_instances()),
                "message_counts": counts,
            })
            return

        if path == "/inbox/all":
            sender = _auth(self)
            if not sender:
                self._json(403, {"error": "Unauthorized"})
                return
            if sender != ADMIN_INSTANCE:
                self._json(403, {"error": "Admin only"})
                return

            try:
                offset = int(qs.get("offset", ["0"])[0])
                limit_raw = qs.get("limit", [None])[0]
                limit = int(limit_raw) if limit_raw is not None else None
                if offset < 0 or (limit is not None and limit < 0):
                    raise ValueError
            except ValueError:
                self._json(400, {"error": "Invalid pagination parameters"})
                return

            _purge_expired()
            all_counts = _db_counts()
            sorted_items = sorted(all_counts.items())
            total_inboxes = len(sorted_items)

            if limit is not None:
                paged_items = sorted_items[offset: offset + limit]
            else:
                paged_items = sorted_items[offset:]

            self._json(200, {
                "inboxes": dict(paged_items),
                "total_inboxes": total_inboxes,
                "limit": limit if limit is not None else total_inboxes,
                "offset": offset,
            })
            return

        if path == "/inbox":
            sender = _auth(self)
            if not sender:
                self._json(403, {"error": "Unauthorized"})
                return

            target = sender
            for_param = qs.get("for", [None])[0]
            if for_param:
                if sender not in PROXY_INSTANCES:
                    self._json(403, {"error": "Proxy access denied"})
                    return
                resolved_target = _resolve_instance(for_param)
                if not resolved_target:
                    self._json(404, {"error": "Unknown instance"})
                    return
                target = resolved_target

            try:
                limit_raw = qs.get("limit", [None])[0]
                limit = int(limit_raw) if limit_raw is not None else None
                offset = int(qs.get("offset", ["0"])[0])
                since_raw = qs.get("since_id", [None])[0]
                since_id = int(since_raw) if since_raw is not None else None
                if offset < 0 or (limit is not None and limit < 0):
                    raise ValueError
            except ValueError:
                self._json(400, {"error": "Invalid query parameters"})
                return

            peek_raw = str(qs.get("peek", ["0"])[0]).lower().strip()
            peek = peek_raw in ("1", "true", "yes")

            _purge_expired()
            msgs = _db_inbox(
                target,
                limit=limit,
                offset=offset,
                since_id=since_id,
                peek=peek,
            )
            self._json(200, {
                "inbox": msgs,
                "count": len(msgs),
                "limit": limit if limit is not None else MAX_INBOX,
                "offset": offset,
                "peek": peek,
            })
            return

        self._json(404, {"error": "Not found"})

    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/admin/register-key":
            sender = _auth(self)
            if not sender:
                self._json(403, {"error": "Unauthorized"})
                return
            if sender != ADMIN_INSTANCE:
                self._json(403, {"error": "Admin only"})
                return

            length = self._parse_content_length()
            if length is None:
                return
            if length > MAX_MSG_BYTES:
                self._json(413, {"error": "Payload too large"})
                return
            try:
                body = json.loads(self.rfile.read(length)) if length > 0 else {}
            except Exception:
                self._json(400, {"error": "Invalid JSON"})
                return

            instance = str(body.get("instance", "")).lower().strip()
            broker_key = str(body.get("broker_key") or body.get("key") or "").strip()
            if not instance or not broker_key:
                self._json(400, {"error": "Missing 'instance' or 'broker_key'"})
                return
            if not _INSTANCE_NAME_RE.match(instance):
                self._json(400, {"error": "Invalid 'instance' name (expected ^[a-z0-9][a-z0-9_-]{0,63}$)"})
                return

            _register_key(instance, broker_key)
            known = _known_instances()
            self._json(200, {
                "ok": True,
                "instance": instance,
                "total_instances": len(known),
            })
            return

        if path == "/admin/reload-keys":
            sender = _auth(self)
            if not sender:
                self._json(403, {"error": "Unauthorized"})
                return
            if sender != ADMIN_INSTANCE:
                self._json(403, {"error": "Admin only"})
                return

            _load_keys()
            known = sorted(_known_with_aliases())
            self._json(200, {
                "ok": True,
                "instances": known,
                "total_instances": len(_known_instances()),
            })
            return

        if path == "/broadcast":
            sender = _auth(self)
            if not sender:
                self._json(403, {"error": "Unauthorized"})
                return
            if sender != ADMIN_INSTANCE:
                self._json(403, {"error": "Admin only"})
                return

            length = self._parse_content_length()
            if length is None:
                return
            if length > MAX_MSG_BYTES * 4:
                self._json(413, {"error": "Payload too large"})
                return

            try:
                body = json.loads(self.rfile.read(length)) if length > 0 else {}
            except Exception:
                self._json(400, {"error": "Invalid JSON"})
                return

            raw_text = body.get("text") if body.get("text") is not None else body.get("message", "")
            text = str(raw_text).strip()
            if not text:
                self._json(400, {"error": "Missing 'text' or 'message'"})
                return
            if len(text.encode()) > MAX_MSG_BYTES:
                self._json(413, {"error": f"Message too large (max {MAX_MSG_BYTES // 1024}KB)"})
                return

            priority = str(body.get("priority", "normal") or "normal").lower().strip()
            if priority not in VALID_PRIORITIES:
                self._json(400, {"error": f"Invalid priority: {priority}"})
                return

            ttl_sec = body.get("ttl_sec")
            if ttl_sec is not None:
                try:
                    ttl_sec = float(ttl_sec)
                    if ttl_sec <= 0:
                        raise ValueError
                except (TypeError, ValueError):
                    self._json(400, {"error": "Invalid 'ttl_sec'"})
                    return

            to_target = body.get("to")
            known = _known_instances()
            if to_target == "*" or to_target == ["*"]:
                recipients = sorted(inst for inst in known if inst != sender)
            elif isinstance(to_target, list):
                raw_list = [str(x).lower().strip() for x in to_target if str(x).strip()]
                if not raw_list:
                    self._json(400, {"error": "Empty 'to' recipient list"})
                    return
                resolved_list = []
                unknown = []
                for r in raw_list:
                    res = _resolve_instance(r)
                    if res is None:
                        unknown.append(r)
                    else:
                        resolved_list.append(res)
                if unknown:
                    self._json(404, {"error": f"Unknown recipients: {', '.join(unknown)}"})
                    return
                recipients = list(dict.fromkeys(r for r in resolved_list if r != sender))
            elif isinstance(to_target, str) and to_target.strip():
                raw_list = [x.lower().strip() for x in to_target.split(",") if x.strip()]
                resolved_list = []
                unknown = []
                for r in raw_list:
                    res = _resolve_instance(r)
                    if res is None:
                        unknown.append(r)
                    else:
                        resolved_list.append(res)
                if unknown:
                    self._json(404, {"error": f"Unknown recipients: {', '.join(unknown)}"})
                    return
                recipients = list(dict.fromkeys(r for r in resolved_list if r != sender))
            else:
                self._json(400, {"error": "Missing or invalid 'to' field"})
                return

            _purge_expired()
            delivered_count = _db_broadcast(
                sender,
                recipients,
                text[:MAX_MSG_BYTES],
                time.time(),
                priority=priority,
                ttl_sec=ttl_sec,
            )
            self._json(200, {
                "ok": True,
                "from": sender,
                "recipients": recipients,
                "delivered_count": delivered_count,
                "count": delivered_count,
                "priority": priority,
            })
            return

        if path != "/send":
            self._json(404, {"error": "Not found"})
            return

        sender = _auth(self)
        if not sender:
            self._json(403, {"error": "Unauthorized"})
            return

        # Rate limit
        if not _send_rl.allow(sender):
            self._json(429, {"error": "Rate limit exceeded (10 msg/min)"})
            return

        length = self._parse_content_length()
        if length is None:
            return
        if length > MAX_MSG_BYTES:
            self._json(413, {"error": f"Message too large (max {MAX_MSG_BYTES // 1024}KB)"})
            return

        try:
            body = json.loads(self.rfile.read(length))
            to = str(body.get("to", "")).lower().strip()
            raw_msg = body.get("message") if body.get("message") is not None else body.get("text", "")
            message = str(raw_msg).strip()
        except Exception:
            self._json(400, {"error": "Invalid JSON"})
            return

        if not to or not message:
            self._json(400, {"error": "Missing 'to' or 'message'"})
            return

        priority = str(body.get("priority", "normal") or "normal").lower().strip()
        if priority not in VALID_PRIORITIES:
            self._json(400, {"error": f"Invalid priority: {priority}"})
            return

        ttl_sec = body.get("ttl_sec")
        if ttl_sec is not None:
            try:
                ttl_sec = float(ttl_sec)
                if ttl_sec <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                self._json(400, {"error": "Invalid 'ttl_sec'"})
                return

        # Proxy: service/admin can send on behalf of another instance
        effective_sender = sender
        on_behalf_of = str(body.get("on_behalf_of", "")).lower().strip()
        if on_behalf_of:
            if sender not in PROXY_INSTANCES:
                self._json(403, {"error": "Proxy send denied"})
                return
            resolved_sender = _resolve_instance(on_behalf_of)
            if not resolved_sender:
                self._json(404, {"error": f"Unknown sender: {on_behalf_of}"})
                return
            effective_sender = resolved_sender

        resolved_to = _resolve_instance(to)
        if not resolved_to:
            self._json(404, {"error": f"Unknown recipient: {to}"})
            return
        if resolved_to == effective_sender:
            self._json(400, {"error": "Cannot send to yourself"})
            return

        _purge_expired()
        msg_id = _db_insert(
            effective_sender,
            resolved_to,
            message[:MAX_MSG_BYTES],
            time.time(),
            priority=priority,
            ttl_sec=ttl_sec,
        )

        print(
            f"[broker] {effective_sender} → {resolved_to} [{priority}]: {message[:60]}"
            + (f" (via {sender})" if effective_sender != sender else ""),
            flush=True,
        )
        self._json(200, {
            "ok": True,
            "id": msg_id,
            "from": effective_sender,
            "to": to,
            "priority": priority,
        })

    def do_DELETE(self):
        parsed = urlparse(self.path)
        if parsed.path != "/inbox":
            self._json(404, {"error": "Not found"})
            return

        sender = _auth(self)
        if not sender:
            self._json(403, {"error": "Unauthorized"})
            return

        target = sender
        qs = parse_qs(parsed.query)
        for_param = qs.get("for", [None])[0]
        if for_param:
            if sender not in PROXY_INSTANCES:
                self._json(403, {"error": "Proxy access denied"})
                return
            resolved_target = _resolve_instance(for_param)
            if not resolved_target:
                self._json(404, {"error": "Unknown instance"})
                return
            target = resolved_target

        count, remaining = _db_clear(target)

        print(
            f"[broker] {target} очистил inbox ({count} сообщений)"
            + (f" (via {sender})" if target != sender else ""),
            flush=True,
        )
        self._json(200, {"ok": True, "deleted": count, "remaining": remaining})


if __name__ == "__main__":
    port = int(os.environ.get("BROKER_PORT", 8080))

    _init_db()
    print(f"[broker] SQLite DB: {BROKER_DB}", flush=True)

    if not _keys:
        print("⚠️  Нет API-ключей!", flush=True)
    else:
        print(f"✅ Broker hardened :{port} | instances: {sorted(_known_instances())}", flush=True)

    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)

    def _shutdown(signum, frame):
        print(f"[broker] Получен сигнал {signum}, завершаем...", flush=True)
        threading.Thread(target=server.shutdown).start()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    server.serve_forever()
