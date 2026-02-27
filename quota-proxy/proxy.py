#!/usr/bin/env python3
"""
corp-assistant / quota-proxy
Прокси между OpenClaw-инстансами и Anthropic API.

Один корпоративный API-ключ — только здесь.
Инстансы используют «квота-ключи» — прокси знает, кто есть кто.

Квоты хранятся в SQLite и меняются через API без рестарта.

Эндпоинты (все доступны только внутри Docker-сети):
  /* (proxy)                      — проксирует на api.anthropic.com
  GET  /quota/health              — статус + список инстансов
  GET  /quota/report[?month=]     — отчёт по использованию
  POST /quota/set-limit           — установить/изменить лимит инстанса
  POST /quota/reset               — сбросить счётчик инстанса
"""

import json, os, sqlite3, threading, time, hashlib
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from urllib.request import Request, urlopen
from urllib.error import HTTPError

# ── Конфиг ─────────────────────────────────────────────────────────────────
UPSTREAM          = "https://api.anthropic.com"
REAL_API_KEY      = os.environ["ANTHROPIC_API_KEY"]
ADMIN_TOKEN       = os.environ.get("QUOTA_ADMIN_TOKEN", "changeme")
DB_PATH           = os.environ.get("QUOTA_DB", "/data/quota.db")
PORT              = int(os.environ.get("QUOTA_PORT", 9090))
DEFAULT_MONTHLY   = int(os.environ.get("QUOTA_DEFAULT_MONTHLY", 1_000_000))

# Квота-ключи: QUOTA_KEY_NIKITA=quota-nikita-xxx → {key: "nikita"}
_quota_keys: dict[str, str] = {}
def _load_keys():
    keys = {}
    for k, v in os.environ.items():
        if k.startswith("QUOTA_KEY_") and v:
            keys[v.strip()] = k[len("QUOTA_KEY_"):].lower()
    return keys
_quota_keys = _load_keys()

# ── SQLite (usage + limits) ────────────────────────────────────────────────
_db_lock = threading.Lock()

def _init_db() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS usage (
            instance TEXT NOT NULL,
            month    TEXT NOT NULL,
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
    """)
    conn.commit()
    # Загружаем начальные лимиты из env (если в БД ещё нет)
    for k, v in os.environ.items():
        if k.startswith("QUOTA_LIMIT_") and v:
            name = k[len("QUOTA_LIMIT_"):].lower()
            try: limit = int(v)
            except ValueError: continue
            conn.execute("""INSERT OR IGNORE INTO limits (instance, monthly_limit, updated_at)
                            VALUES (?, ?, ?)""", (name, limit, time.strftime("%Y-%m-%dT%H:%M:%S")))
    conn.commit()
    return conn

_conn = _init_db()

# ── Работа с лимитами ──────────────────────────────────────────────────────
def _get_limit(instance: str) -> int:
    """Возвращает лимит из БД (или DEFAULT_MONTHLY)."""
    with _db_lock:
        row = _conn.execute(
            "SELECT monthly_limit FROM limits WHERE instance=?", (instance,)).fetchone()
    return row[0] if row else DEFAULT_MONTHLY

def _set_limit(instance: str, limit: int, by: str = "admin") -> None:
    """Устанавливает лимит в БД — без рестарта."""
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    with _db_lock:
        _conn.execute("""INSERT INTO limits (instance, monthly_limit, updated_at, updated_by)
                         VALUES (?, ?, ?, ?)
                         ON CONFLICT(instance) DO UPDATE SET
                             monthly_limit = excluded.monthly_limit,
                             updated_at    = excluded.updated_at,
                             updated_by    = excluded.updated_by""",
                      (instance, limit, now, by))
        _conn.commit()

def _get_all_limits() -> dict[str, dict]:
    with _db_lock:
        rows = _conn.execute(
            "SELECT instance, monthly_limit, updated_at, updated_by FROM limits").fetchall()
    return {r[0]: {"limit": r[1], "updated_at": r[2], "updated_by": r[3]} for r in rows}

# ── Работа с usage ─────────────────────────────────────────────────────────
def _add_usage(instance: str, inp: int, out: int):
    month = time.strftime("%Y-%m")
    with _db_lock:
        _conn.execute("""INSERT INTO usage (instance, month, input_tokens, output_tokens, requests)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(instance, month) DO UPDATE SET
                input_tokens  = input_tokens  + excluded.input_tokens,
                output_tokens = output_tokens + excluded.output_tokens,
                requests      = requests + 1""",
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

def _get_all_usage(month: str = None) -> list[dict]:
    month = month or time.strftime("%Y-%m")
    all_limits = _get_all_limits()
    with _db_lock:
        rows = _conn.execute(
            "SELECT instance, input_tokens, output_tokens, requests FROM usage WHERE month=? "
            "ORDER BY (input_tokens+output_tokens) DESC", (month,)).fetchall()
    result = []
    for inst, inp, out, reqs in rows:
        total = inp + out
        limit = all_limits.get(inst, {}).get("limit", DEFAULT_MONTHLY)
        pct   = round(total / limit * 100, 1) if limit > 0 else None
        result.append({
            "instance":      inst,
            "month":         month,
            "input_tokens":  inp,
            "output_tokens": out,
            "total_tokens":  total,
            "requests":      reqs,
            "limit":         limit if limit > 0 else "unlimited",
            "used_pct":      pct,
            "status":        "❌ exceeded" if (limit>0 and total>=limit)
                             else "⚠️ warning" if (limit>0 and total/limit>=0.8)
                             else "✅ ok"
        })
    return result

def _check_quota(instance: str) -> tuple[bool, str]:
    limit = _get_limit(instance)
    if limit <= 0: return True, ""
    total = _get_usage(instance)["total"]
    if total >= limit:
        return False, (f"Квота {instance} исчерпана: {total:,} / {limit:,} токенов в месяц. "
                       f"Обратись к администратору.")
    return True, ""

def _reset_usage(instance: str, month: str = None):
    month = month or time.strftime("%Y-%m")
    with _db_lock:
        _conn.execute("DELETE FROM usage WHERE instance=? AND month=?", (instance, month))
        _conn.commit()

# ── HTTP Handler ───────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        print(f"[quota] {self.address_string()} {fmt % args}", flush=True)

    def _json(self, code: int, body):
        data = json.dumps(body, ensure_ascii=False, indent=2).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(data))
        self.end_headers()
        self.wfile.write(data)

    def _is_admin(self) -> bool:
        return self.headers.get("Authorization") == f"Bearer {ADMIN_TOKEN}"

    def _get_instance(self) -> str | None:
        return _quota_keys.get(self.headers.get("x-api-key", ""))

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length)) if length else {}

    # ── GET ──────────────────────────────────────────────────────────────
    def do_GET(self):
        path = urlparse(self.path).path
        qs   = parse_qs(urlparse(self.path).query)

        if path == "/quota/health":
            self._json(200, {
                "status":    "ok",
                "instances": sorted(set(_quota_keys.values())),
                "limits":    _get_all_limits()
            })
            return

        if path == "/quota/report":
            if not self._is_admin():
                self._json(403, {"error": "Unauthorized"}); return
            month = qs.get("month", [time.strftime("%Y-%m")])[0]
            self._json(200, {"month": month, "usage": _get_all_usage(month),
                             "limits": _get_all_limits()})
            return

        self._proxy("GET")

    # ── POST ─────────────────────────────────────────────────────────────
    def do_POST(self):
        path = urlparse(self.path).path

        # ── Установить лимит (без рестарта!) ─────────────────────────────
        if path == "/quota/set-limit":
            if not self._is_admin():
                self._json(403, {"error": "Unauthorized"}); return
            body = self._read_json()
            instance = str(body.get("instance", "")).lower().strip()
            limit    = body.get("limit")
            if not instance or limit is None:
                self._json(400, {"error": "Нужны поля: instance, limit"}); return
            try: limit = int(limit)
            except (ValueError, TypeError):
                self._json(400, {"error": "limit должен быть числом"}); return

            _set_limit(instance, limit, by="admin-api")
            current = _get_usage(instance)["total"]
            print(f"[quota] SET LIMIT {instance}: {limit:,} (текущий расход: {current:,})", flush=True)
            self._json(200, {
                "ok":       True,
                "instance": instance,
                "limit":    limit,
                "current_usage": current,
                "status":   "❌ exceeded" if (limit>0 and current>=limit)
                            else "⚠️ warning" if (limit>0 and limit>0 and current/limit>=0.8)
                            else "✅ ok"
            })
            return

        # ── Сбросить счётчик ─────────────────────────────────────────────
        if path == "/quota/reset":
            if not self._is_admin():
                self._json(403, {"error": "Unauthorized"}); return
            body     = self._read_json()
            instance = str(body.get("instance", "")).lower().strip()
            month    = body.get("month", time.strftime("%Y-%m"))
            if not instance:
                self._json(400, {"error": "Нужно поле: instance"}); return
            _reset_usage(instance, month)
            print(f"[quota] RESET {instance} {month}", flush=True)
            self._json(200, {"ok": True, "reset": instance, "month": month})
            return

        self._proxy("POST")

    # ── Прокси на Anthropic ───────────────────────────────────────────────
    def _proxy(self, method: str):
        instance = self._get_instance()
        if instance is None:
            self._json(401, {"error": "Unknown quota key. Обратись к администратору."}); return

        ok, msg = _check_quota(instance)
        if not ok:
            self._json(429, {"type": "error", "error": "quota_exceeded", "message": msg}); return

        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length) if length else b""

        headers = {
            "x-api-key":         REAL_API_KEY,
            "anthropic-version": self.headers.get("anthropic-version", "2023-06-01"),
            "content-type":      self.headers.get("content-type", "application/json"),
        }
        if self.headers.get("anthropic-beta"):
            headers["anthropic-beta"] = self.headers["anthropic-beta"]

        try:
            req = Request(UPSTREAM + self.path, data=body or None,
                          headers=headers, method=method)
            with urlopen(req, timeout=120) as r:
                resp_body, resp_status = r.read(), r.status
                resp_ct = r.headers.get("Content-Type", "application/json")
        except HTTPError as e:
            resp_body, resp_status, resp_ct = e.read(), e.code, "application/json"

        # Считаем токены
        try:
            usage = json.loads(resp_body).get("usage", {})
            inp, out = usage.get("input_tokens", 0), usage.get("output_tokens", 0)
            if inp or out:
                _add_usage(instance, inp, out)
                total = _get_usage(instance)["total"]
                limit = _get_limit(instance)
                pct   = f"{total/limit*100:.0f}%" if limit > 0 else "∞"
                print(f"[quota] {instance}: +{inp+out} → {total:,}/{limit:,} ({pct})", flush=True)
        except Exception:
            pass

        self.send_response(resp_status)
        self.send_header("Content-Type", resp_ct)
        self.send_header("Content-Length", len(resp_body))
        self.end_headers()
        self.wfile.write(resp_body)


if __name__ == "__main__":
    print(f"✅ Quota-proxy :{PORT} | instances: {sorted(set(_quota_keys.values()))} | db: {DB_PATH}", flush=True)
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
