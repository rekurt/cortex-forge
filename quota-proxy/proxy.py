#!/usr/bin/env python3
"""
CortexForge Proxy — token quota enforcement  [hardened]

Единственное место, где хранится настоящий Anthropic API-ключ.
Инстансы используют квота-ключи — proxy определяет кто есть кто.

Hardening:
  - Constant-time token comparison (нет timing-атаки)
  - Rate limiting: leaky bucket per IP/instance
  - Max request body size
  - SQLite WAL mode (нет deadlock под нагрузкой)
  - Audit log всех admin-операций
  - Security headers в ответах
  - Лимиты в SQLite (переживают рестарт, меняются без рестарта)
"""

from __future__ import annotations
import json, os, pwd, grp, re, signal, sqlite3, threading, time, hmac, hashlib
from contextlib import contextmanager
from http.server import HTTPServer, ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

# ── Конфиг ─────────────────────────────────────────────────────────────────
UPSTREAM_URL     = os.environ.get("UPSTREAM_URL", "https://api.anthropic.com").rstrip("/")
UPSTREAM_API_KEY = os.environ.get("UPSTREAM_API_KEY", "")
REAL_API_KEY     = os.environ.get("ANTHROPIC_API_KEY", "")
ADMIN_TOKEN      = os.environ.get("QUOTA_ADMIN_TOKEN", "")

# Ключ для upstream: UPSTREAM_API_KEY приоритетнее, fallback на ANTHROPIC_API_KEY
_upstream_key    = UPSTREAM_API_KEY or REAL_API_KEY
# Определяем режим работы: CLIProxyAPI или прямой Anthropic
_is_cliproxy     = "api.anthropic.com" not in UPSTREAM_URL

if not _upstream_key:
    raise RuntimeError("Ни UPSTREAM_API_KEY, ни ANTHROPIC_API_KEY не заданы — proxy не может работать без ключа")
DB_PATH          = os.environ.get("QUOTA_DB", "/data/quota.db")
PORT             = int(os.environ.get("QUOTA_PORT", 9090))
DEFAULT_MONTHLY  = int(os.environ.get("QUOTA_DEFAULT_MONTHLY", 1_000_000))
MAX_BODY_BYTES   = 1 * 1024 * 1024   # 1 MB — защита от giant request

if not ADMIN_TOKEN:
    raise RuntimeError("QUOTA_ADMIN_TOKEN не задан — запуск небезопасен")

_INSTANCE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_KEY_HASH_RE = re.compile(r"^[0-9a-fA-F]{64}$")
MAX_SSE_LINE_BYTES = 65536

# Квота-ключи: QUOTA_KEY_USER_1=quota-user-1-xxx → {key_hash: "user-1"}
# Храним sha256 хэш, а не сам ключ — чтобы ключ не жил в памяти как plaintext
_keys_lock = threading.RLock()
_quota_keys: dict[str, str] = {}   # {sha256(key): instance_name}
_departments: dict[str, str] = {}  # {instance_name: department}
_instance_departments = _departments
_admin_hash: str = ""
_conn: sqlite3.Connection | None = None

def _load_keys():
    global _quota_keys, _departments, _instance_departments, _admin_hash
    keys: dict[str, str] = {}
    depts: dict[str, str] = {}
    for k, v in os.environ.items():
        if k.startswith("QUOTA_KEY_") and v:
            raw_suffix = k[len("QUOTA_KEY_"):]
            name = raw_suffix.lower().strip()
            hyphen_name = name.replace("_", "-")
            if v.strip().lower().startswith(f"quota-{hyphen_name}-"):
                name = hyphen_name
            dept_env = (
                os.environ.get(f"QUOTA_DEPT_{raw_suffix.upper()}")
                or os.environ.get(f"QUOTA_DEPT_{name.upper()}")
                or "default"
            ).strip().lower() or "default"
            keys[hashlib.sha256(v.strip().encode()).hexdigest()] = name
            depts[name] = dept_env
    if _conn is not None:
        try:
            with _db_lock:
                rows = _conn.execute("SELECT instance, key_hash, department FROM quota_keys").fetchall()
            for inst, khash, dept in rows:
                inst = inst.lower().strip()
                # Удаляем старый хэш этого инстанса (если был из env), чтобы ротация работала атомарно
                stale = [h for h, n in keys.items() if n == inst]
                for h in stale:
                    del keys[h]
                keys[khash] = inst
                depts[inst] = (dept or "default").strip().lower() or "default"
        except sqlite3.Error:
            pass
    with _keys_lock:
        _quota_keys = keys
        _departments = depts
        _instance_departments = _departments
        _admin_hash = hashlib.sha256(ADMIN_TOKEN.encode()).hexdigest()

_load_keys()

# ── Rate Limiter (leaky bucket) ─────────────────────────────────────────────
class RateLimiter:
    """Leaky bucket: max N tokens, rефиллится со скоростью rate/sec."""
    def __init__(self, rate: float, capacity: int):
        self.rate     = rate
        self.capacity = capacity
        self._buckets: dict[str, tuple[float, float]] = {}
        self._b       = self._buckets
        self._lock    = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            if len(self._buckets) > 10000:
                stale_keys = [k for k, (_, ts) in self._buckets.items() if now - ts > 120]
                for k in stale_keys:
                    del self._buckets[k]
            tokens, last = self._buckets.get(key, (self.capacity, now))
            tokens = min(self.capacity, tokens + (now - last) * self.rate)
            if tokens < 1:
                self._buckets[key] = (tokens, now)
                return False
            self._buckets[key] = (tokens - 1, now)
            return True

# 60 admin-запросов в минуту с одного IP
_admin_rl  = RateLimiter(rate=1.0, capacity=60)
# 300 proxy-запросов в минуту с одного инстанса (≈ 5/сек)
_proxy_rl  = RateLimiter(rate=5.0, capacity=300)
# 10 broker-сообщений в минуту с инстанса
_broker_rl = RateLimiter(rate=0.17, capacity=10)

# ── SQLite ─────────────────────────────────────────────────────────────────
_db_lock = threading.RLock()
_admission_meta_lock = threading.Lock()
_instance_admission_locks: dict[str, threading.RLock] = {}
_dept_admission_locks: dict[str, threading.RLock] = {}

def _get_instance_admission_lock(instance: str) -> threading.RLock:
    with _admission_meta_lock:
        lock = _instance_admission_locks.get(instance)
        if lock is None:
            lock = threading.RLock()
            _instance_admission_locks[instance] = lock
        return lock

def _get_dept_admission_lock(department: str) -> threading.RLock:
    with _admission_meta_lock:
        lock = _dept_admission_locks.get(department)
        if lock is None:
            lock = threading.RLock()
            _dept_admission_locks[department] = lock
        return lock

@contextmanager
def _quota_admission_guard(instance: str):
    """Сериализует окно check_quota -> upstream -> add_usage для одного инстанса (и департамента с лимитом)."""
    dept = _get_department(instance)
    dept_limit = _get_department_limit(dept)
    inst_lock = _get_instance_admission_lock(instance)
    if dept_limit > 0:
        dept_lock = _get_dept_admission_lock(dept)
        with dept_lock:
            with inst_lock:
                yield
    else:
        with inst_lock:
            yield

def _now(): return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def _init_db() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10.0, check_same_thread=False)
    # WAL mode + busy_timeout: выдерживает 1000 конкурентных пользователей без блокировок
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA journal_size_limit=1048576")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS usage (
            instance      TEXT NOT NULL,
            month         TEXT NOT NULL,
            input_tokens  INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            requests      INTEGER DEFAULT 0,
            PRIMARY KEY (instance, month)
        );
        CREATE INDEX IF NOT EXISTS idx_usage_month_instance ON usage(month, instance);
        CREATE TABLE IF NOT EXISTS limits (
            instance      TEXT PRIMARY KEY,
            monthly_limit INTEGER NOT NULL,
            updated_at    TEXT NOT NULL,
            updated_by    TEXT DEFAULT 'system'
        );
        CREATE TABLE IF NOT EXISTS quota_keys (
            instance   TEXT PRIMARY KEY,
            key_hash   TEXT NOT NULL,
            department TEXT DEFAULT 'default',
            updated_at INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_quota_keys_department ON quota_keys(department);
        CREATE TABLE IF NOT EXISTS department_limits (
            department    TEXT PRIMARY KEY,
            monthly_limit INTEGER NOT NULL,
            updated_at    TEXT NOT NULL,
            updated_by    TEXT DEFAULT 'system'
        );
        CREATE TABLE IF NOT EXISTS audit_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            ts         TEXT NOT NULL,
            action     TEXT NOT NULL,
            actor      TEXT NOT NULL,
            target     TEXT,
            detail     TEXT
        );
    """)
    conn.commit()
    # Начальные лимиты из env (только если в БД ещё нет)
    for k, v in os.environ.items():
        if k.startswith("QUOTA_LIMIT_") and v:
            name = k[len("QUOTA_LIMIT_"):].lower().strip().replace("_", "-")
            try: limit = int(v)
            except ValueError: continue
            conn.execute("INSERT OR IGNORE INTO limits (instance, monthly_limit, updated_at, updated_by) VALUES (?,?,?,'env')",
                         (name, limit, _now()))
    conn.commit()
    return conn

def _drop_privileges(user: str = "app"):
    """
    Если процесс запущен от root — исправляем владение /data и дропаем привилегии.
    Это нужно для миграции существующих томов (root:root → app:app) при обновлении
    контейнера с новым non-root пользователем.
    """
    if os.getuid() != 0:
        return  # уже не root, ничего не делаем
    try:
        pw  = pwd.getpwnam(user)
        uid = pw.pw_uid
        gid = pw.pw_gid
    except KeyError:
        print(f"[quota] WARNING: user '{user}' not found, staying as root", flush=True)
        return

    # Исправляем владение /data (включая все файлы внутри)
    data_dir = os.environ.get("QUOTA_DB", "/data/quota.db")
    data_root = os.path.dirname(data_dir)
    if os.path.isdir(data_root):
        os.lchown(data_root, uid, gid)
        for dirpath, dirnames, filenames in os.walk(data_root):
            for name in dirnames + filenames:
                try:
                    os.lchown(os.path.join(dirpath, name), uid, gid)
                except OSError:
                    pass

    # Дропаем привилегии: сначала GID, потом UID (порядок важен)
    os.setgid(gid)
    os.setgroups([gid])
    os.setuid(uid)
    print(f"[quota] Dropped privileges: uid={uid} gid={gid} ({user})", flush=True)


_drop_privileges()   # ← вызываем ДО открытия БД (чтобы открыть с правильным uid)
_conn = _init_db()
_load_keys()         # ← загружаем ключи из env + таблицы quota_keys

def _audit(action: str, actor: str, target: str = None, detail: str = None):
    with _db_lock:
        _conn.execute("INSERT INTO audit_log (ts, action, actor, target, detail) VALUES (?,?,?,?,?)",
                      (_now(), action, actor, target, detail))
        _conn.commit()

# ── Динамические ключи и департаменты ──────────────────────────────────────
def _get_department(instance: str) -> str:
    with _keys_lock:
        dept = _departments.get(instance)
    if dept:
        return dept
    with _db_lock:
        row = _conn.execute("SELECT department FROM quota_keys WHERE instance=?", (instance,)).fetchone()
    if row and row[0]:
        dept = row[0].strip().lower() or "default"
        with _keys_lock:
            _departments[instance] = dept
        return dept
    return "default"

def _register_key(instance: str, raw_key: str = None, key_hash: str = None,
                  department: str = "default", limit: int | None = None, by: str = "admin-api") -> str:
    instance = instance.lower().strip()
    if not _INSTANCE_RE.match(instance):
        raise ValueError("Недопустимое имя инстанса (ожидается ^[a-z0-9][a-z0-9_-]{0,63}$)")
    department = (department or "default").strip().lower() or "default"
    if not _INSTANCE_RE.match(department):
        raise ValueError("Недопустимое имя департамента")
    if raw_key and str(raw_key).strip():
        key_hash = hashlib.sha256(str(raw_key).strip().encode()).hexdigest()
    elif key_hash and str(key_hash).strip():
        key_hash = str(key_hash).strip().lower()
        if not _KEY_HASH_RE.match(key_hash):
            raise ValueError("Некорректный key_hash (ожидается 64 hex-символа SHA256)")
    else:
        raise ValueError("Required quota_key or key_hash")
    now_ts = int(time.time())
    with _db_lock:
        _conn.execute("""INSERT INTO quota_keys (instance, key_hash, department, updated_at)
                         VALUES (?,?,?,?)
                         ON CONFLICT(instance) DO UPDATE SET
                             key_hash=excluded.key_hash,
                             department=excluded.department,
                             updated_at=excluded.updated_at""",
                      (instance, key_hash, department, now_ts))
        if limit is not None:
            _conn.execute("""INSERT INTO limits (instance, monthly_limit, updated_at, updated_by)
                             VALUES (?,?,?,?)
                             ON CONFLICT(instance) DO UPDATE SET
                                 monthly_limit=excluded.monthly_limit,
                                 updated_at=excluded.updated_at,
                                 updated_by=excluded.updated_by""",
                          (instance, int(limit), _now(), by))
        _conn.commit()
    with _keys_lock:
        stale = [h for h, n in _quota_keys.items() if n == instance]
        for h in stale:
            del _quota_keys[h]
        _quota_keys[key_hash] = instance
        _departments[instance] = department
    return key_hash

def _get_department_limit(department: str) -> int:
    department = (department or "default").strip().lower() or "default"
    with _db_lock:
        row = _conn.execute("SELECT monthly_limit FROM department_limits WHERE department=?", (department,)).fetchone()
    return row[0] if row else 0

def _set_department_limit(department: str, limit: int, by: str = "admin-api"):
    department = (department or "default").strip().lower() or "default"
    with _db_lock:
        _conn.execute("""INSERT INTO department_limits (department, monthly_limit, updated_at, updated_by)
                         VALUES (?,?,?,?)
                         ON CONFLICT(department) DO UPDATE SET
                             monthly_limit=excluded.monthly_limit,
                             updated_at=excluded.updated_at,
                             updated_by=excluded.updated_by""",
                      (department, int(limit), _now(), by))
        _conn.commit()

def _get_all_department_limits() -> dict:
    with _db_lock:
        rows = _conn.execute("SELECT department, monthly_limit, updated_at, updated_by FROM department_limits").fetchall()
    return {r[0]: {"limit": r[1], "updated_at": r[2], "updated_by": r[3]} for r in rows}

def _get_department_usage(department: str, month: str = None) -> int:
    month = month or time.strftime("%Y-%m")
    department = (department or "default").strip().lower() or "default"
    with _keys_lock:
        dept_cache = dict(_departments)
    with _db_lock:
        rows = _conn.execute(
            """SELECT u.instance, u.input_tokens, u.output_tokens, q.department
               FROM usage u
               LEFT JOIN quota_keys q ON u.instance = q.instance
               WHERE u.month = ?""",
            (month,),
        ).fetchall()
    total = 0
    for inst, inp, out, db_dept in rows:
        inst_dept = (db_dept or dept_cache.get(inst) or "default").strip().lower() or "default"
        if inst_dept == department:
            total += (inp or 0) + (out or 0)
    return total

# ── Лимиты ─────────────────────────────────────────────────────────────────
def _get_limit(instance: str) -> int:
    with _db_lock:
        row = _conn.execute("SELECT monthly_limit FROM limits WHERE instance=?", (instance,)).fetchone()
    return row[0] if row else DEFAULT_MONTHLY

def _set_limit(instance: str, limit: int, by: str):
    with _db_lock:
        _conn.execute("""INSERT INTO limits (instance, monthly_limit, updated_at, updated_by)
                         VALUES (?,?,?,?)
                         ON CONFLICT(instance) DO UPDATE SET
                             monthly_limit=excluded.monthly_limit,
                             updated_at=excluded.updated_at,
                             updated_by=excluded.updated_by""",
                      (instance, limit, _now(), by))
        _conn.commit()

def _get_all_limits() -> dict:
    with _db_lock:
        rows = _conn.execute("SELECT instance, monthly_limit, updated_at, updated_by FROM limits").fetchall()
    return {r[0]: {"limit": r[1], "updated_at": r[2], "updated_by": r[3]} for r in rows}

# ── Usage ───────────────────────────────────────────────────────────────────
def _add_usage(instance: str, inp: int, out: int):
    month = time.strftime("%Y-%m")
    with _db_lock:
        _conn.execute("""INSERT INTO usage (instance, month, input_tokens, output_tokens, requests)
            VALUES (?,?,?,?,1)
            ON CONFLICT(instance, month) DO UPDATE SET
                input_tokens=input_tokens+excluded.input_tokens,
                output_tokens=output_tokens+excluded.output_tokens,
                requests=requests+1""",
            (instance, month, inp, out))
        _conn.commit()

def _get_usage(instance: str, month: str = None) -> dict:
    month = month or time.strftime("%Y-%m")
    with _db_lock:
        row = _conn.execute(
            "SELECT input_tokens, output_tokens, requests FROM usage WHERE instance=? AND month=?",
            (instance, month)).fetchone()
    if not row: return {"input": 0, "output": 0, "total": 0, "requests": 0}
    return {"input": row[0], "output": row[1], "total": row[0]+row[1], "requests": row[2]}

def _get_all_usage(month: str = None, department: str = None, status_filter: str = None) -> list:
    month = month or time.strftime("%Y-%m")
    limits = _get_all_limits()
    with _db_lock:
        rows = _conn.execute(
            "SELECT instance, input_tokens, output_tokens, requests FROM usage WHERE month=? "
            "ORDER BY (input_tokens+output_tokens) DESC, instance ASC", (month,)).fetchall()
    dept_filter = department.strip().lower() if department else None
    norm_status = status_filter.strip().lower() if status_filter else None
    result = []
    for inst, inp, out, reqs in rows:
        dept = _get_department(inst)
        if dept_filter and dept != dept_filter:
            continue
        total = inp + out
        limit = limits.get(inst, {}).get("limit", DEFAULT_MONTHLY)
        pct   = round(total/limit*100, 1) if limit > 0 else None
        status = ("❌ exceeded" if limit>0 and total>=limit
                  else "⚠️ warning" if limit>0 and pct>=80
                  else "✅ ok")
        if norm_status:
            # Поддерживаем фильтр как по 'ok'/'warning'/'exceeded', так и по полному статусу
            status_code = "exceeded" if "exceeded" in status else "warning" if "warning" in status else "ok"
            if norm_status not in (status_code, status.lower()):
                continue
        result.append({"instance": inst, "department": dept, "month": month,
                        "input_tokens": inp, "output_tokens": out,
                        "total_tokens": total, "requests": reqs,
                        "limit": limit if limit>0 else "unlimited",
                        "used_pct": pct, "status": status})
    return result

def _get_departments_summary(month: str = None) -> dict:
    month = month or time.strftime("%Y-%m")
    dept_limits = _get_all_department_limits()
    with _db_lock:
        rows = _conn.execute(
            "SELECT instance, input_tokens, output_tokens, requests FROM usage WHERE month=?",
            (month,)).fetchall()
    summary: dict[str, dict] = {}
    for dept_name, info in dept_limits.items():
        summary[dept_name] = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "requests": 0,
            "instances": 0,
        }
    for inst, inp, out, reqs in rows:
        dept = _get_department(inst)
        entry = summary.setdefault(dept, {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "requests": 0,
            "instances": 0,
        })
        entry["input_tokens"] += inp or 0
        entry["output_tokens"] += out or 0
        entry["total_tokens"] += (inp or 0) + (out or 0)
        entry["requests"] += reqs or 0
        entry["instances"] += 1
    for dept, entry in summary.items():
        dlim = dept_limits.get(dept, {}).get("limit", 0)
        total = entry["total_tokens"]
        pct = round(total / dlim * 100, 1) if dlim > 0 else None
        status = ("❌ exceeded" if dlim > 0 and total >= dlim
                  else "⚠️ warning" if dlim > 0 and pct >= 80
                  else "✅ ok")
        entry["limit"] = dlim if dlim > 0 else "unlimited"
        entry["used_pct"] = pct
        entry["status"] = status
    return summary

def _check_quota(instance: str) -> tuple[bool, str]:
    limit = _get_limit(instance)
    if limit > 0:
        total = _get_usage(instance)["total"]
        if total >= limit:
            return False, f"Квота {instance} исчерпана: {total:,}/{limit:,} токенов. Обратись к администратору."
    dept = _get_department(instance)
    dept_limit = _get_department_limit(dept)
    if dept_limit > 0:
        dept_total = _get_department_usage(dept)
        if dept_total >= dept_limit:
            return False, f"Квота департамента {dept} исчерпана: {dept_total:,}/{dept_limit:,} токенов. Обратись к администратору."
    return True, ""

def _reset_usage(instance: str, month: str = None):
    month = month or time.strftime("%Y-%m")
    with _db_lock:
        _conn.execute("DELETE FROM usage WHERE instance=? AND month=?", (instance, month))
        _conn.commit()

# ── SSE Usage Parser ───────────────────────────────────────────────────────
class SSEUsageParser:
    """Потоковый парсер SSE-событий Anthropic и OpenAI для учёта токенов без задержки стрима."""

    def __init__(self):
        self.input_tokens: int = 0
        self.output_tokens: int = 0
        self._current_event: str = ""
        self._remainder: bytes = b""

    def feed_chunk(self, chunk: bytes):
        if not chunk:
            return
        data = self._remainder + chunk
        lines = data.split(b"\n")
        self._remainder = lines.pop()
        if len(self._remainder) > MAX_SSE_LINE_BYTES:
            self._remainder = self._remainder[-MAX_SSE_LINE_BYTES:]
        for raw_line in lines:
            self.feed_line(raw_line)

    def finish(self):
        if self._remainder:
            self.feed_line(self._remainder)
            self._remainder = b""

    def feed_line(self, raw_line: bytes | str):
        line = raw_line.decode("utf-8", errors="replace") if isinstance(raw_line, bytes) else raw_line
        line = line.strip("\r\n").strip()
        if not line:
            self._current_event = ""
            return
        if line.startswith("event:"):
            self._current_event = line[6:].strip()
            return
        if not line.startswith("data:"):
            return
        data_str = line[5:].strip()
        if not data_str or data_str == "[DONE]":
            return
        try:
            payload = json.loads(data_str)
        except Exception:
            return
        if not isinstance(payload, dict):
            return

        ev_type = payload.get("type") or self._current_event

        # Anthropic: message_start -> message.usage.input_tokens
        if ev_type == "message_start":
            msg = payload.get("message")
            if isinstance(msg, dict):
                u = msg.get("usage")
                if isinstance(u, dict):
                    if u.get("input_tokens") is not None:
                        self.input_tokens = int(u["input_tokens"])
                    if u.get("output_tokens") is not None and self.output_tokens == 0:
                        self.output_tokens = int(u["output_tokens"])
            return

        # Anthropic: message_delta -> usage.output_tokens
        if ev_type == "message_delta":
            u = payload.get("usage")
            if isinstance(u, dict):
                if u.get("input_tokens") is not None and int(u["input_tokens"]) > 0:
                    self.input_tokens = int(u["input_tokens"])
                if u.get("output_tokens") is not None:
                    self.output_tokens = int(u["output_tokens"])
            return

        # OpenAI / совместимые SSE: data: {... "usage": {"prompt_tokens": ..., "completion_tokens": ...}}
        u = payload.get("usage")
        if isinstance(u, dict):
            if u.get("prompt_tokens") is not None:
                self.input_tokens = int(u["prompt_tokens"])
            elif u.get("input_tokens") is not None:
                self.input_tokens = int(u["input_tokens"])
            if u.get("completion_tokens") is not None:
                self.output_tokens = int(u["completion_tokens"])
            elif u.get("output_tokens") is not None:
                self.output_tokens = int(u["output_tokens"])


def _parse_sse_usage(raw_body: bytes | str) -> tuple[int, int]:
    parser = SSEUsageParser()
    if isinstance(raw_body, bytes):
        parser.feed_chunk(raw_body)
        parser.finish()
    else:
        for line in raw_body.splitlines():
            parser.feed_line(line)
    return parser.input_tokens, parser.output_tokens


# ── HTTP Handler ────────────────────────────────────────────────────────────
_SEC_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Cache-Control": "no-store",
}

class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        print(f"[quota] {self.address_string()} {self.command} {self.path} | {fmt % args}", flush=True)

    def _json(self, code: int, body):
        data = json.dumps(body, ensure_ascii=False, indent=2).encode()
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", len(data))
            for k, v in _SEC_HEADERS.items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)
        except BrokenPipeError:
            pass

    # Constant-time сравнение — нет timing-атаки
    def _is_admin(self) -> bool:
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "): return False
        provided = hashlib.sha256(auth[7:].encode()).hexdigest()
        return hmac.compare_digest(provided, _admin_hash)

    def _get_instance(self) -> str | None:
        key = self.headers.get("x-api-key", "")
        if not key:
            # Агент с ANTHROPIC_BASE_URL может слать Authorization: Bearer
            auth = self.headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                key = auth[7:]
        if not key: return None
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        # Constant-time поиск под RLock — не раскрывает наличие ключа через время
        with _keys_lock:
            items = list(_quota_keys.items())
        result = None
        for h, name in items:
            if hmac.compare_digest(key_hash, h):
                result = name
        return result

    def _read_body(self) -> bytes | None:
        """Читает тело с лимитом размера и валидацией Content-Length."""
        raw_len = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_len)
        except (ValueError, TypeError):
            self.close_connection = True
            self._json(400, {"error": "Invalid Content-Length"})
            return None
        if length < 0:
            self.close_connection = True
            self._json(400, {"error": "Invalid Content-Length"})
            return None
        if length > MAX_BODY_BYTES:
            self.close_connection = True
            self._json(413, {"error": "Request body too large (max 1MB)"})
            return None
        return self.rfile.read(length) if length else b""

    def _client_ip(self) -> str:
        return self.client_address[0]

    # ── GET ───────────────────────────────────────────────────────────────
    def do_GET(self):
        path = urlparse(self.path).path
        qs   = parse_qs(urlparse(self.path).query)

        if path == "/quota/health":
            with _keys_lock:
                instances = sorted(set(_quota_keys.values()))
            self._json(200, {"status": "ok",
                             "instances": instances,
                             "limits": _get_all_limits()})
            return

        if path == "/quota/report":
            if not _admin_rl.allow(self._client_ip()):
                self._json(429, {"error": "Rate limit exceeded"}); return
            if not self._is_admin():
                _audit("REPORT_DENIED", self._client_ip())
                self._json(403, {"error": "Unauthorized"}); return
            month = qs.get("month", [time.strftime("%Y-%m")])[0]
            department = qs.get("department", [None])[0]
            status_filter = qs.get("status", [None])[0]
            try:
                page_limit = int(qs["limit"][0]) if "limit" in qs and qs["limit"][0] != "" else None
                page_offset = int(qs.get("offset", ["0"])[0])
                if page_offset < 0 or (page_limit is not None and page_limit < 0):
                    raise ValueError("negative pagination")
            except ValueError:
                self._json(400, {"error": "Некорректные параметры limit/offset"}); return

            all_usage = _get_all_usage(month, department=department, status_filter=status_filter)
            total_instances = len(all_usage)
            if page_limit is not None:
                paged_usage = all_usage[page_offset:page_offset + page_limit]
            elif page_offset:
                paged_usage = all_usage[page_offset:]
            else:
                paged_usage = all_usage

            _audit("REPORT", "admin", detail=f"month={month}")
            self._json(200, {"month": month,
                             "usage": paged_usage,
                             "total_instances": total_instances,
                             "limits": _get_all_limits(),
                             "departments": _get_departments_summary(month)})
            return

        self._proxy("GET")

    # ── POST ──────────────────────────────────────────────────────────────
    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/quota/set-limit":
            if not _admin_rl.allow(self._client_ip()):
                self._json(429, {"error": "Rate limit exceeded"}); return
            if not self._is_admin():
                _audit("SET_LIMIT_DENIED", self._client_ip())
                self._json(403, {"error": "Unauthorized"}); return
            body_raw = self._read_body()
            if body_raw is None:
                return
            try:
                body = json.loads(body_raw)
                instance = str(body["instance"]).lower().strip()
                limit    = int(body["limit"])
            except (KeyError, ValueError, TypeError):
                self._json(400, {"error": "Нужны поля: instance (str), limit (int)"}); return
            # Валидация имени инстанса
            if not _INSTANCE_RE.match(instance):
                self._json(400, {"error": "Недопустимое имя инстанса"}); return
            _set_limit(instance, limit, by="admin-api")
            _audit("SET_LIMIT", "admin", target=instance, detail=f"limit={limit}")
            current = _get_usage(instance)["total"]
            print(f"[quota] SET_LIMIT {instance}={limit:,} (usage={current:,})", flush=True)
            self._json(200, {"ok": True, "instance": instance, "limit": limit,
                             "current_usage": current})
            return

        if path == "/quota/register-key":
            if not _admin_rl.allow(self._client_ip()):
                self._json(429, {"error": "Rate limit exceeded"}); return
            if not self._is_admin():
                _audit("REGISTER_KEY_DENIED", self._client_ip())
                self._json(403, {"error": "Unauthorized"}); return
            body_raw = self._read_body()
            if body_raw is None:
                return
            try:
                body = json.loads(body_raw)
                instance = str(body["instance"]).lower().strip()
                quota_key = body.get("quota_key") or body.get("key")
                key_hash = body.get("key_hash")
                department = str(body.get("department", "default")).lower().strip() or "default"
                limit_val = int(body["limit"]) if body.get("limit") is not None else None
            except (KeyError, ValueError, TypeError):
                self._json(400, {"error": "Нужны поля: instance (str), quota_key или key_hash (str)"}); return
            if not _INSTANCE_RE.match(instance):
                self._json(400, {"error": "Недопустимое имя инстанса"}); return
            if not _INSTANCE_RE.match(department):
                self._json(400, {"error": "Недопустимое имя департамента"}); return
            if not quota_key and not key_hash:
                self._json(400, {"error": "Нужно поле quota_key или key_hash"}); return
            if not quota_key and key_hash and not _KEY_HASH_RE.match(str(key_hash).strip()):
                self._json(400, {"error": "Некорректный key_hash (ожидается 64 hex-символа SHA256)"}); return
            try:
                saved_hash = _register_key(instance, raw_key=str(quota_key) if quota_key else None,
                                           key_hash=str(key_hash) if key_hash else None,
                                           department=department, limit=limit_val, by="admin-api")
            except ValueError as e:
                self._json(400, {"error": str(e)}); return
            _audit("REGISTER_KEY", "admin", target=instance, detail=f"dept={department} limit={limit_val}")
            self._json(200, {"ok": True, "instance": instance, "key_hash": saved_hash,
                             "department": department, "limit": _get_limit(instance)})
            return

        if path == "/quota/reload-keys":
            if not _admin_rl.allow(self._client_ip()):
                self._json(429, {"error": "Rate limit exceeded"}); return
            if not self._is_admin():
                _audit("RELOAD_KEYS_DENIED", self._client_ip())
                self._json(403, {"error": "Unauthorized"}); return
            _load_keys()
            with _keys_lock:
                instances = sorted(set(_quota_keys.values()))
                total_keys = len(_quota_keys)
            _audit("RELOAD_KEYS", "admin", detail=f"total_keys={total_keys}")
            self._json(200, {"ok": True, "instances": instances, "total_keys": total_keys})
            return

        if path == "/quota/set-department-limit":
            if not _admin_rl.allow(self._client_ip()):
                self._json(429, {"error": "Rate limit exceeded"}); return
            if not self._is_admin():
                _audit("SET_DEPT_LIMIT_DENIED", self._client_ip())
                self._json(403, {"error": "Unauthorized"}); return
            body_raw = self._read_body()
            if body_raw is None:
                return
            try:
                body = json.loads(body_raw)
                department = str(body["department"]).lower().strip()
                limit = int(body["limit"])
            except (KeyError, ValueError, TypeError):
                self._json(400, {"error": "Нужны поля: department (str), limit (int)"}); return
            if not _INSTANCE_RE.match(department):
                self._json(400, {"error": "Недопустимое имя департамента"}); return
            _set_department_limit(department, limit, by="admin-api")
            _audit("SET_DEPT_LIMIT", "admin", target=department, detail=f"limit={limit}")
            current = _get_department_usage(department)
            self._json(200, {"ok": True, "department": department, "limit": limit,
                             "current_usage": current})
            return

        if path == "/quota/reset":
            if not _admin_rl.allow(self._client_ip()):
                self._json(429, {"error": "Rate limit exceeded"}); return
            if not self._is_admin():
                _audit("RESET_DENIED", self._client_ip())
                self._json(403, {"error": "Unauthorized"}); return
            body_raw = self._read_body()
            if body_raw is None:
                return
            try:
                body     = json.loads(body_raw)
                instance = str(body["instance"]).lower().strip()
                month    = str(body.get("month", time.strftime("%Y-%m")))
            except (KeyError, ValueError):
                self._json(400, {"error": "Нужно поле: instance"}); return
            _reset_usage(instance, month)
            _audit("RESET", "admin", target=instance, detail=f"month={month}")
            print(f"[quota] RESET {instance} {month}", flush=True)
            self._json(200, {"ok": True, "reset": instance, "month": month})
            return

        self._proxy("POST")

    # ── Proxy → Anthropic ─────────────────────────────────────────────────
    def _proxy(self, method: str):
        instance = self._get_instance()
        if instance is None:
            self._json(401, {"error": "Unknown quota key"}); return

        # Rate limit на инстанс
        if not _proxy_rl.allow(instance):
            self._json(429, {"error": "Rate limit exceeded for instance"}); return

        body_raw = self._read_body()
        if body_raw is None:
            return

        with _quota_admission_guard(instance):
            ok, msg = _check_quota(instance)
            if not ok:
                _audit("QUOTA_BLOCKED", instance)
                self._json(429, {"type": "error", "error": "quota_exceeded", "message": msg}); return

            headers = {
                "anthropic-version": self.headers.get("anthropic-version", "2023-06-01"),
                "content-type":      self.headers.get("content-type", "application/json"),
            }

            if _is_cliproxy:
                # CLIProxyAPI: всегда x-api-key, без OAuth-бет, с User-Agent для обхода cloaking
                headers["x-api-key"] = _upstream_key
                headers["User-Agent"] = "claude-cli/2.1.44 (external, sdk-cli)"
                if v := self.headers.get("anthropic-beta"):
                    headers["anthropic-beta"] = v
            elif _upstream_key.startswith("sk-ant-oat"):
                # Прямой Anthropic с OAuth-ключом
                headers["Authorization"] = f"Bearer {_upstream_key}"
                oauth_betas = ["claude-code-20250219", "oauth-2025-04-20"]
                existing = self.headers.get("anthropic-beta", "")
                existing_list = [b.strip() for b in existing.split(",") if b.strip()]
                all_betas = list(dict.fromkeys(oauth_betas + existing_list))
                headers["anthropic-beta"] = ",".join(all_betas)
            else:
                # Прямой Anthropic с обычным API-ключом
                headers["x-api-key"] = _upstream_key
                if v := self.headers.get("anthropic-beta"):
                    headers["anthropic-beta"] = v

            try:
                req = Request(UPSTREAM_URL + self.path, data=body_raw or None,
                              headers=headers, method=method)
                with urlopen(req, timeout=120) as r:
                    resp_status = r.status
                    resp_ct = r.headers.get("Content-Type", "application/json")
                    if "event-stream" in resp_ct.lower():
                        self._stream_sse(r, resp_status, resp_ct, instance)
                        return
                    resp_body = r.read()
            except HTTPError as e:
                resp_body, resp_status, resp_ct = e.read(), e.code, e.headers.get("Content-Type", "application/json")
            except URLError as e:
                print(f"[quota] UPSTREAM ERROR {instance}: {e}", flush=True)
                self._json(502, {"type": "error", "error": "upstream_unavailable",
                                 "message": f"Anthropic API недоступен: {e.reason}"}); return
            except Exception as e:
                print(f"[quota] UNEXPECTED ERROR {instance}: {e}", flush=True)
                self._json(502, {"type": "error", "error": "proxy_error",
                                 "message": "Внутренняя ошибка proxy"}); return

            # Считаем токены из ответа (JSON или буферизованный text/event-stream)
            try:
                if "event-stream" in resp_ct.lower():
                    inp, out = _parse_sse_usage(resp_body)
                else:
                    usage = json.loads(resp_body).get("usage", {})
                    inp = usage.get("input_tokens") if usage.get("input_tokens") is not None else usage.get("prompt_tokens", 0)
                    out = usage.get("output_tokens") if usage.get("output_tokens") is not None else usage.get("completion_tokens", 0)
                if inp or out:
                    self._record_usage_log(instance, int(inp), int(out))
            except Exception as e:
                if "event-stream" not in resp_ct.lower():
                    print(f"[quota] WARNING: failed to parse usage from response for {instance}: {e}", flush=True)

        self.send_response(resp_status)
        self.send_header("Content-Type", resp_ct)
        self.send_header("Content-Length", len(resp_body))
        for k, v in _SEC_HEADERS.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(resp_body)

    def _record_usage_log(self, instance: str, inp: int, out: int):
        _add_usage(instance, inp, out)
        total = _get_usage(instance)["total"]
        limit = _get_limit(instance)
        pct   = f"{total/limit*100:.0f}%" if limit > 0 else "∞"
        lvl   = "⚠️" if limit>0 and total/limit>=0.8 else "  "
        print(f"[quota] {lvl} {instance}: +{inp+out} → {total:,}/{limit:,} ({pct})", flush=True)

    def _stream_sse(self, upstream_resp, resp_status: int, resp_ct: str, instance: str):
        """Потоковая передача SSE клиенту без буферизации с подсчётом токенов на лету."""
        parser = SSEUsageParser()
        try:
            self.send_response(resp_status)
            self.send_header("Content-Type", resp_ct)
            for k, v in _SEC_HEADERS.items():
                self.send_header(k, v)
            self.end_headers()
            while True:
                line = upstream_resp.readline(MAX_SSE_LINE_BYTES)
                if not line:
                    break
                parser.feed_chunk(line)
                try:
                    self.wfile.write(line)
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    break
            parser.finish()
        finally:
            self.close_connection = True
            inp, out = parser.input_tokens, parser.output_tokens
            if inp or out:
                self._record_usage_log(instance, int(inp), int(out))


if __name__ == "__main__":
    with _keys_lock:
        instances = sorted(set(_quota_keys.values()))
    upstream_mode = "CLIProxyAPI" if _is_cliproxy else "Anthropic API (direct)"
    print(f"✅ Quota-proxy hardened :{PORT}", flush=True)
    print(f"   Upstream: {UPSTREAM_URL} ({upstream_mode})", flush=True)
    print(f"   Инстансы: {instances}", flush=True)
    print(f"   DB: {DB_PATH} (WAL mode)", flush=True)
    print(f"   Max body: {MAX_BODY_BYTES//1024}KB", flush=True)

    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)

    def _shutdown(signum, frame):
        print(f"[quota] Получен сигнал {signum}, завершаем...", flush=True)
        def _do():
            server.shutdown()   # ждёт завершения всех in-flight запросов
            _conn.close()       # закрываем DB только после полной остановки HTTP
        threading.Thread(target=_do, daemon=True).start()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    server.serve_forever()
