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

import json, os, pwd, grp, signal, sqlite3, threading, time, hmac, hashlib, collections
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

# ── Конфиг ─────────────────────────────────────────────────────────────────
UPSTREAM         = "https://api.anthropic.com"
REAL_API_KEY     = os.environ.get("ANTHROPIC_API_KEY", "")
ADMIN_TOKEN      = os.environ.get("QUOTA_ADMIN_TOKEN", "")

if not REAL_API_KEY:
    raise RuntimeError("ANTHROPIC_API_KEY не задан — proxy не может работать без реального ключа")
DB_PATH          = os.environ.get("QUOTA_DB", "/data/quota.db")
PORT             = int(os.environ.get("QUOTA_PORT", 9090))
DEFAULT_MONTHLY  = int(os.environ.get("QUOTA_DEFAULT_MONTHLY", 1_000_000))
MAX_BODY_BYTES   = 1 * 1024 * 1024   # 1 MB — защита от giant request

if not ADMIN_TOKEN:
    raise RuntimeError("QUOTA_ADMIN_TOKEN не задан — запуск небезопасен")

# Квота-ключи: QUOTA_KEY_USER_1=quota-user-1-xxx → {key_hash: "user-1"}
# Храним sha256 хэш, а не сам ключ — чтобы ключ не жил в памяти как plaintext
_quota_keys: dict[str, str] = {}   # {sha256(key): instance_name}
_admin_hash: str = ""

def _load_keys():
    global _quota_keys, _admin_hash
    keys = {}
    for k, v in os.environ.items():
        if k.startswith("QUOTA_KEY_") and v:
            name = k[len("QUOTA_KEY_"):].lower()
            keys[hashlib.sha256(v.strip().encode()).hexdigest()] = name
    _quota_keys = keys
    _admin_hash = hashlib.sha256(ADMIN_TOKEN.encode()).hexdigest()

_load_keys()

# ── Rate Limiter (leaky bucket) ─────────────────────────────────────────────
class RateLimiter:
    """Leaky bucket: max N tokens, rефиллится со скоростью rate/sec."""
    def __init__(self, rate: float, capacity: int):
        self.rate     = rate
        self.capacity = capacity
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock    = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
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
_db_lock = threading.Lock()

def _init_db() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    # WAL mode: намного лучше под нагрузкой (readers не блокируют writer)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS usage (
            instance      TEXT NOT NULL,
            month         TEXT NOT NULL,
            input_tokens  INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            requests      INTEGER DEFAULT 0,
            PRIMARY KEY (instance, month)
        );
        CREATE TABLE IF NOT EXISTS limits (
            instance      TEXT PRIMARY KEY,
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
            name = k[len("QUOTA_LIMIT_"):].lower()
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


def _now(): return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

_drop_privileges()   # ← вызываем ДО открытия БД (чтобы открыть с правильным uid)
_conn = _init_db()

def _audit(action: str, actor: str, target: str = None, detail: str = None):
    with _db_lock:
        _conn.execute("INSERT INTO audit_log (ts, action, actor, target, detail) VALUES (?,?,?,?,?)",
                      (_now(), action, actor, target, detail))
        _conn.commit()

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

def _get_all_usage(month: str = None) -> list:
    month = month or time.strftime("%Y-%m")
    limits = _get_all_limits()
    with _db_lock:
        rows = _conn.execute(
            "SELECT instance, input_tokens, output_tokens, requests FROM usage WHERE month=? "
            "ORDER BY (input_tokens+output_tokens) DESC", (month,)).fetchall()
    result = []
    for inst, inp, out, reqs in rows:
        total = inp + out
        limit = limits.get(inst, {}).get("limit", DEFAULT_MONTHLY)
        pct   = round(total/limit*100, 1) if limit > 0 else None
        status = ("❌ exceeded" if limit>0 and total>=limit
                  else "⚠️ warning" if limit>0 and pct>=80
                  else "✅ ok")
        result.append({"instance": inst, "month": month,
                        "input_tokens": inp, "output_tokens": out,
                        "total_tokens": total, "requests": reqs,
                        "limit": limit if limit>0 else "unlimited",
                        "used_pct": pct, "status": status})
    return result

def _check_quota(instance: str) -> tuple[bool, str]:
    limit = _get_limit(instance)
    if limit <= 0: return True, ""
    total = _get_usage(instance)["total"]
    if total >= limit:
        return False, f"Квота {instance} исчерпана: {total:,}/{limit:,} токенов. Обратись к администратору."
    return True, ""

def _reset_usage(instance: str, month: str = None):
    month = month or time.strftime("%Y-%m")
    with _db_lock:
        _conn.execute("DELETE FROM usage WHERE instance=? AND month=?", (instance, month))
        _conn.commit()

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
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(data))
        for k, v in _SEC_HEADERS.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    # Constant-time сравнение — нет timing-атаки
    def _is_admin(self) -> bool:
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "): return False
        provided = hashlib.sha256(auth[7:].encode()).hexdigest()
        return hmac.compare_digest(provided, _admin_hash)

    def _get_instance(self) -> str | None:
        key = self.headers.get("x-api-key", "")
        if not key:
            # OpenClaw с ANTHROPIC_BASE_URL может слать Authorization: Bearer
            auth = self.headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                key = auth[7:]
        if not key: return None
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        # Constant-time поиск — не раскрывает наличие ключа через время
        result = None
        for h, name in _quota_keys.items():
            if hmac.compare_digest(key_hash, h):
                result = name
        return result

    def _read_body(self) -> bytes | None:
        """Читает тело с лимитом размера."""
        length = int(self.headers.get("Content-Length", 0))
        if length > MAX_BODY_BYTES:
            return None  # тело слишком большое
        return self.rfile.read(length) if length else b""

    def _client_ip(self) -> str:
        return self.client_address[0]

    # ── GET ───────────────────────────────────────────────────────────────
    def do_GET(self):
        path = urlparse(self.path).path
        qs   = parse_qs(urlparse(self.path).query)

        if path == "/quota/health":
            self._json(200, {"status": "ok",
                             "instances": sorted(set(_quota_keys.values())),
                             "limits": _get_all_limits()})
            return

        if path == "/quota/report":
            if not _admin_rl.allow(self._client_ip()):
                self._json(429, {"error": "Rate limit exceeded"}); return
            if not self._is_admin():
                _audit("REPORT_DENIED", self._client_ip())
                self._json(403, {"error": "Unauthorized"}); return
            month = qs.get("month", [time.strftime("%Y-%m")])[0]
            _audit("REPORT", "admin", detail=f"month={month}")
            self._json(200, {"month": month,
                             "usage": _get_all_usage(month),
                             "limits": _get_all_limits()})
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
                self._json(413, {"error": "Request too large"}); return
            try:
                body = json.loads(body_raw)
                instance = str(body["instance"]).lower().strip()
                limit    = int(body["limit"])
            except (KeyError, ValueError, TypeError):
                self._json(400, {"error": "Нужны поля: instance (str), limit (int)"}); return
            # Валидация имени инстанса
            if not instance.replace("-", "").replace("_", "").isalnum():
                self._json(400, {"error": "Недопустимое имя инстанса"}); return
            _set_limit(instance, limit, by="admin-api")
            _audit("SET_LIMIT", "admin", target=instance, detail=f"limit={limit}")
            current = _get_usage(instance)["total"]
            print(f"[quota] SET_LIMIT {instance}={limit:,} (usage={current:,})", flush=True)
            self._json(200, {"ok": True, "instance": instance, "limit": limit,
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
                self._json(413, {"error": "Request too large"}); return
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

        ok, msg = _check_quota(instance)
        if not ok:
            _audit("QUOTA_BLOCKED", instance)
            self._json(429, {"type": "error", "error": "quota_exceeded", "message": msg}); return

        body_raw = self._read_body()
        if body_raw is None:
            self._json(413, {"error": "Request body too large (max 1MB)"}); return

        headers = {
            "x-api-key":         REAL_API_KEY,
            "anthropic-version": self.headers.get("anthropic-version", "2023-06-01"),
            "content-type":      self.headers.get("content-type", "application/json"),
        }
        if v := self.headers.get("anthropic-beta"):
            headers["anthropic-beta"] = v

        try:
            req = Request(UPSTREAM + self.path, data=body_raw or None,
                          headers=headers, method=method)
            with urlopen(req, timeout=120) as r:
                resp_body, resp_status = r.read(), r.status
                resp_ct = r.headers.get("Content-Type", "application/json")
        except HTTPError as e:
            resp_body, resp_status, resp_ct = e.read(), e.code, "application/json"
        except URLError as e:
            print(f"[quota] UPSTREAM ERROR {instance}: {e}", flush=True)
            self._json(502, {"type": "error", "error": "upstream_unavailable",
                             "message": f"Anthropic API недоступен: {e.reason}"}); return
        except Exception as e:
            print(f"[quota] UNEXPECTED ERROR {instance}: {e}", flush=True)
            self._json(502, {"type": "error", "error": "proxy_error",
                             "message": "Внутренняя ошибка proxy"}); return

        # Считаем токены из ответа
        try:
            usage = json.loads(resp_body).get("usage", {})
            inp, out = usage.get("input_tokens", 0), usage.get("output_tokens", 0)
            if inp or out:
                _add_usage(instance, inp, out)
                total = _get_usage(instance)["total"]
                limit = _get_limit(instance)
                pct   = f"{total/limit*100:.0f}%" if limit > 0 else "∞"
                lvl   = "⚠️" if limit>0 and total/limit>=0.8 else "  "
                print(f"[quota] {lvl} {instance}: +{inp+out} → {total:,}/{limit:,} ({pct})", flush=True)
        except Exception:
            pass

        self.send_response(resp_status)
        self.send_header("Content-Type", resp_ct)
        self.send_header("Content-Length", len(resp_body))
        for k, v in _SEC_HEADERS.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(resp_body)


if __name__ == "__main__":
    instances = sorted(set(_quota_keys.values()))
    print(f"✅ Quota-proxy hardened :{PORT}", flush=True)
    print(f"   Инстансы: {instances}", flush=True)
    print(f"   DB: {DB_PATH} (WAL mode)", flush=True)
    print(f"   Max body: {MAX_BODY_BYTES//1024}KB", flush=True)

    server = HTTPServer(("0.0.0.0", PORT), Handler)

    def _shutdown(signum, frame):
        print(f"[quota] Получен сигнал {signum}, завершаем...", flush=True)
        def _do():
            server.shutdown()   # ждёт завершения всех in-flight запросов
            _conn.close()       # закрываем DB только после полной остановки HTTP
        threading.Thread(target=_do, daemon=True).start()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    server.serve_forever()
