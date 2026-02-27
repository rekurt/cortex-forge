#!/usr/bin/env python3
"""
corp-assistant / message broker
Безопасная шина сообщений между инстансами ассистентов.

Каждый инстанс идентифицируется своим API-ключом.
Отправить можно только от своего имени — подделать sender нельзя.
Читать можно только свой inbox.

API:
  POST /send   {to: "name", message: "text"}   → 200 / 403 / 404
  GET  /inbox                                   → [{from, message, ts}]
  GET  /health                                  → 200
"""

import json
import os
import time
import hashlib
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from collections import defaultdict, deque
from urllib.parse import urlparse

# ── Конфиг ────────────────────────────────────────────────────────────────
# Ключи берутся из env: BROKER_KEY_NIKITA=xxx BROKER_KEY_ALEXEY=yyy ...
MAX_INBOX   = 100     # максимум сообщений в inbox
MAX_AGE_SEC = 86400   # удалять сообщения старше 24ч

# ── Состояние ─────────────────────────────────────────────────────────────
_lock   = threading.Lock()
_inbox  = defaultdict(deque)     # {name: deque([{from, message, ts}])}
_keys   = {}                     # {api_key_hash: name}

def _load_keys():
    """Загружает API-ключи из env-переменных BROKER_KEY_<NAME>=<key>."""
    keys = {}
    for k, v in os.environ.items():
        if k.startswith("BROKER_KEY_") and v:
            name = k[len("BROKER_KEY_"):].lower()
            keys[hashlib.sha256(v.encode()).hexdigest()] = name
    return keys

_keys = _load_keys()

def _auth(req) -> str | None:
    """Возвращает имя инстанса по Authorization: Bearer <key> или None."""
    auth = req.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    key_hash = hashlib.sha256(auth[7:].encode()).hexdigest()
    return _keys.get(key_hash)

def _cleanup():
    """Удаляет устаревшие сообщения."""
    cutoff = time.time() - MAX_AGE_SEC
    with _lock:
        for name in list(_inbox.keys()):
            q = _inbox[name]
            while q and q[0]["ts"] < cutoff:
                q.popleft()

# ── HTTP обработчик ────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        print(f"[broker] {self.address_string()} {fmt % args}", flush=True)

    def _respond(self, code: int, body: dict):
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(data))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/health":
            self._respond(200, {"status": "ok", "instances": list(set(_keys.values()))})
            return

        if path == "/inbox":
            sender = _auth(self)
            if not sender:
                self._respond(403, {"error": "Unauthorized"})
                return
            _cleanup()
            with _lock:
                msgs = list(_inbox[sender])
            self._respond(200, {"inbox": msgs, "count": len(msgs)})
            return

        self._respond(404, {"error": "Not found"})

    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/send":
            sender = _auth(self)
            if not sender:
                self._respond(403, {"error": "Unauthorized"})
                return

            length = int(self.headers.get("Content-Length", 0))
            try:
                body = json.loads(self.rfile.read(length))
            except Exception:
                self._respond(400, {"error": "Invalid JSON"})
                return

            to      = str(body.get("to", "")).lower().strip()
            message = str(body.get("message", "")).strip()

            if not to or not message:
                self._respond(400, {"error": "Missing 'to' or 'message'"})
                return

            # Получатель должен быть известным инстансом
            known = set(_keys.values())
            if to not in known:
                self._respond(404, {"error": f"Unknown recipient: {to}"})
                return

            if to == sender:
                self._respond(400, {"error": "Cannot send to yourself"})
                return

            msg = {"from": sender, "to": to, "message": message, "ts": time.time()}
            with _lock:
                q = _inbox[to]
                if len(q) >= MAX_INBOX:
                    q.popleft()
                q.append(msg)

            print(f"[broker] {sender} → {to}: {message[:60]}", flush=True)
            self._respond(200, {"ok": True, "from": sender, "to": to})
            return

        self._respond(404, {"error": "Not found"})


if __name__ == "__main__":
    port = int(os.environ.get("BROKER_PORT", 8080))
    if not _keys:
        print("⚠️  Нет API-ключей. Задай BROKER_KEY_<NAME>=<secret> в env.", flush=True)
    else:
        print(f"✅ Broker запущен на :{port}, инстансы: {sorted(set(_keys.values()))}", flush=True)
    server = HTTPServer(("0.0.0.0", port), Handler)
    server.serve_forever()
