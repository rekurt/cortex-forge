#!/usr/bin/env python3
"""
corp-assistant / quota-proxy
Прокси между OpenClaw-инстансами и Anthropic API.

Каждый инстанс получает свой «квота-ключ» вместо настоящего API-ключа.
Прокси: считает токены → хранит в SQLite → режет при превышении лимита.

Эндпоинты:
  /* (proxy)          — проксирует запросы на api.anthropic.com
  GET  /quota/report  — отчёт по использованию всех инстансов
  GET  /quota/reset?instance=x  — сброс счётчика (только для admin-ключа)
  GET  /quota/health  — статус
"""

import json
import os
import sqlite3
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, urlencode, parse_qs
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import calendar

# ── Конфиг ─────────────────────────────────────────────────────────────────
UPSTREAM        = "https://api.anthropic.com"
REAL_API_KEY    = os.environ["ANTHROPIC_API_KEY"]   # настоящий ключ Anthropic
ADMIN_TOKEN     = os.environ.get("QUOTA_ADMIN_TOKEN", "changeme")
DB_PATH         = os.environ.get("QUOTA_DB", "/data/quota.db")
PORT            = int(os.environ.get("QUOTA_PORT", 9090))
DEFAULT_MONTHLY = int(os.environ.get("QUOTA_DEFAULT_MONTHLY", 1_000_000))  # токенов/мес

# Квота-ключи → имена инстансов.
# Читаются из env: QUOTA_KEY_NIKITA=quota-nikita-xxx
# Лимиты из env:   QUOTA_LIMIT_NIKITA=500000  (токенов в месяц, 0=без лимита)
_quota_keys: dict[str, str] = {}   # {quota_key: instance_name}
_limits:     dict[str, int] = {}   # {instance_name: monthly_limit}

def _load_keys():
    global _quota_keys, _limits
    keys, limits = {}, {}
    for k, v in os.environ.items():
        if k.startswith("QUOTA_KEY_") and v:
            name = k[len("QUOTA_KEY_"):].lower()
            keys[v.strip()] = name
        if k.startswith("QUOTA_LIMIT_") and v:
            name = k[len("QUOTA_LIMIT_"):].lower()
            try: limits[name] = int(v)
            except ValueError: pass
    _quota_keys, _limits = keys, limits

_load_keys()

# ── SQLite ─────────────────────────────────────────────────────────────────
_db_lock = threading.Lock()

def _db() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("""CREATE TABLE IF NOT EXISTS usage (
        instance TEXT NOT NULL,
        month    TEXT NOT NULL,   -- YYYY-MM
        input_tokens  INTEGER DEFAULT 0,
        output_tokens INTEGER DEFAULT 0,
        requests      INTEGER DEFAULT 0,
        PRIMARY KEY (instance, month)
    )""")
    conn.commit()
    return conn

_conn = _db()

def _add_usage(instance: str, input_tok: int, output_tok: int):
    month = time.strftime("%Y-%m")
    with _db_lock:
        _conn.execute("""INSERT INTO usage (instance, month, input_tokens, output_tokens, requests)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(instance, month) DO UPDATE SET
                input_tokens  = input_tokens  + excluded.input_tokens,
                output_tokens = output_tokens + excluded.output_tokens,
                requests      = requests + 1""",
            (instance, month, input_tok, output_tok))
        _conn.commit()

def _get_usage(instance: str, month: str = None) -> dict:
    month = month or time.strftime("%Y-%m")
    with _db_lock:
        row = _conn.execute(
            "SELECT input_tokens, output_tokens, requests FROM usage WHERE instance=? AND month=?",
            (instance, month)).fetchone()
    if not row:
        return {"input": 0, "output": 0, "total": 0, "requests": 0}
    return {"input": row[0], "output": row[1], "total": row[0] + row[1], "requests": row[2]}

def _get_all_usage(month: str = None) -> list[dict]:
    month = month or time.strftime("%Y-%m")
    with _db_lock:
        rows = _conn.execute(
            "SELECT instance, input_tokens, output_tokens, requests FROM usage WHERE month=? ORDER BY (input_tokens+output_tokens) DESC",
            (month,)).fetchall()
    results = []
    for r in rows:
        inst, inp, out, reqs = r
        limit = _limits.get(inst, DEFAULT_MONTHLY)
        total = inp + out
        pct   = round(total / limit * 100, 1) if limit > 0 else None
        results.append({
            "instance": inst,
            "month": month,
            "input_tokens":  inp,
            "output_tokens": out,
            "total_tokens":  total,
            "requests":      reqs,
            "limit":         limit if limit > 0 else "unlimited",
            "used_pct":      pct,
            "status": _quota_status(inst, total)
        })
    return results

def _quota_status(instance: str, total: int) -> str:
    limit = _limits.get(instance, DEFAULT_MONTHLY)
    if limit <= 0: return "unlimited"
    pct = total / limit
    if pct >= 1.0: return "❌ exceeded"
    if pct >= 0.8: return "⚠️ warning"
    return "✅ ok"

def _check_quota(instance: str) -> tuple[bool, str]:
    """True если квота не превышена."""
    limit = _limits.get(instance, DEFAULT_MONTHLY)
    if limit <= 0:
        return True, ""
    usage = _get_usage(instance)
    total = usage["total"]
    if total >= limit:
        return False, (f"Квота {instance} исчерпана: {total:,} / {limit:,} токенов в месяц. "
                       f"Обратись к администратору.")
    return True, ""

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

    def _get_instance(self) -> str | None:
        """Определяет инстанс по x-api-key заголовку."""
        key = self.headers.get("x-api-key", "")
        return _quota_keys.get(key)

    # ── Служебные эндпоинты ──────────────────────────────────────────────
    def do_GET(self):
        path = urlparse(self.path).path
        qs   = parse_qs(urlparse(self.path).query)

        if path == "/quota/health":
            self._json(200, {
                "status": "ok",
                "instances": sorted(set(_quota_keys.values())),
                "db": DB_PATH
            })
            return

        if path == "/quota/report":
            # Только admin-токен
            if self.headers.get("Authorization") != f"Bearer {ADMIN_TOKEN}":
                self._json(403, {"error": "Unauthorized"})
                return
            month = qs.get("month", [time.strftime("%Y-%m")])[0]
            self._json(200, {"month": month, "usage": _get_all_usage(month)})
            return

        if path == "/quota/reset":
            if self.headers.get("Authorization") != f"Bearer {ADMIN_TOKEN}":
                self._json(403, {"error": "Unauthorized"})
                return
            instance = qs.get("instance", [None])[0]
            month    = qs.get("month", [time.strftime("%Y-%m")])[0]
            if not instance:
                self._json(400, {"error": "?instance= required"})
                return
            with _db_lock:
                _conn.execute("DELETE FROM usage WHERE instance=? AND month=?", (instance, month))
                _conn.commit()
            self._json(200, {"ok": True, "reset": instance, "month": month})
            return

        # Проксируем GET запросы на Anthropic
        self._proxy("GET")

    def do_POST(self):
        self._proxy("POST")

    def _proxy(self, method: str):
        instance = self._get_instance()

        # Неизвестный ключ — отказываем
        if instance is None:
            self._json(401, {"error": "Unknown quota key. Обратись к администратору."})
            return

        # Проверка квоты ПЕРЕД запросом
        ok, msg = _check_quota(instance)
        if not ok:
            self._json(429, {"error": "quota_exceeded", "message": msg,
                             "type": "error"})
            return

        # Читаем тело запроса
        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length) if length else b""

        # Собираем заголовки для апстрима (подменяем ключ на настоящий)
        headers = {
            "x-api-key":    REAL_API_KEY,
            "anthropic-version": self.headers.get("anthropic-version", "2023-06-01"),
            "content-type": self.headers.get("content-type", "application/json"),
        }
        if self.headers.get("anthropic-beta"):
            headers["anthropic-beta"] = self.headers["anthropic-beta"]

        url = UPSTREAM + self.path
        try:
            req = Request(url, data=body or None, headers=headers, method=method)
            with urlopen(req, timeout=120) as resp:
                resp_body   = resp.read()
                resp_status = resp.status
                resp_headers = dict(resp.headers)
        except HTTPError as e:
            resp_body   = e.read()
            resp_status = e.code
            resp_headers = {}

        # Парсим использование токенов из ответа
        input_tok, output_tok = 0, 0
        try:
            parsed = json.loads(resp_body)
            usage  = parsed.get("usage", {})
            input_tok  = usage.get("input_tokens", 0)
            output_tok = usage.get("output_tokens", 0)
        except Exception:
            pass

        if input_tok or output_tok:
            _add_usage(instance, input_tok, output_tok)
            total = _get_usage(instance)["total"]
            limit = _limits.get(instance, DEFAULT_MONTHLY)
            pct   = f"{total/limit*100:.0f}%" if limit > 0 else "∞"
            print(f"[quota] {instance}: +{input_tok+output_tok} tok "
                  f"(total {total:,} / {limit:,} = {pct})", flush=True)

        # Отдаём ответ клиенту
        self.send_response(resp_status)
        for h in ("content-type", "x-request-id"):
            if h in resp_headers:
                self.send_header(h, resp_headers[h])
        self.send_header("Content-Length", len(resp_body))
        self.end_headers()
        self.wfile.write(resp_body)


if __name__ == "__main__":
    known = sorted(set(_quota_keys.values()))
    print(f"✅ Quota-proxy запущен на :{PORT}", flush=True)
    print(f"   Инстансы: {known}", flush=True)
    print(f"   Лимиты:   {_limits}", flush=True)
    print(f"   DB:       {DB_PATH}", flush=True)
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    server.serve_forever()
