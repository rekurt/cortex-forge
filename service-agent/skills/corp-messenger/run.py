#!/usr/bin/env python3
"""
Corp Messenger — межинстансный мессенджер CortexForge.

Skill для service-agent. Читает JSON из stdin, пишет JSON в stdout.
Все HTTP через urllib.request (stdlib only, без curl).

Service-agent выступает прокси: broker позволяет ему читать/отправлять
от имени caller'а через on_behalf_of (send) и ?for= (inbox/clear).

Actions:
  send  — отправить сообщение другому инстансу
  inbox — прочитать входящие caller'а
  clear — очистить inbox caller'а
  list  — показать доступные инстансы (без auth)
"""

import json
import os
import sys
import urllib.request
import urllib.error

BROKER_URL = os.environ.get("BROKER_URL", "http://message-broker:8080")
BROKER_KEY = os.environ.get("BROKER_KEY", "")

TIMEOUT = 10  # seconds for HTTP requests


def _request(method, path, data=None, auth=True):
    """Make HTTP request to broker. Returns (status_code, parsed_json)."""
    url = f"{BROKER_URL}{path}"
    headers = {"Content-Type": "application/json"}
    if auth and BROKER_KEY:
        headers["Authorization"] = f"Bearer {BROKER_KEY}"

    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            err_body = json.loads(e.read().decode())
        except Exception:
            err_body = {"error": e.reason}
        return e.code, err_body
    except urllib.error.URLError as e:
        return 0, {"error": f"Connection failed: {e.reason}"}
    except Exception as e:
        return 0, {"error": str(e)}


def action_send(params, caller):
    """POST /send — отправить сообщение от имени caller'а."""
    to = params.get("to", "").strip()
    message = params.get("message", "").strip()

    if not to:
        return {"status": "error", "error": "Missing 'to' parameter"}
    if not message:
        return {"status": "error", "error": "Missing 'message' parameter"}

    payload = {"to": to, "message": message}
    if caller:
        payload["on_behalf_of"] = caller

    code, body = _request("POST", "/send", payload)

    if code == 200:
        return {"status": "ok", "message": f"Sent to {to}", "detail": body}
    elif code == 403:
        return {"status": "error", "error": "Authentication failed — check BROKER_KEY"}
    elif code == 429:
        return {"status": "error", "error": "Rate limit exceeded (10 msg/min)"}
    elif code == 404:
        return {"status": "error", "error": f"Unknown recipient: {to}"}
    elif code == 400:
        return {"status": "error", "error": body.get("error", "Bad request")}
    else:
        return {"status": "error", "error": body.get("error", f"HTTP {code}")}


def action_inbox(params, caller):
    """GET /inbox?for=<caller> — прочитать входящие сообщения caller'а."""
    path = "/inbox"
    if caller:
        path = f"/inbox?for={caller}"

    code, body = _request("GET", path)

    if code == 200:
        inbox = body.get("inbox", [])
        count = body.get("count", len(inbox))
        return {"status": "ok", "count": count, "inbox": inbox}
    elif code == 403:
        return {"status": "error", "error": "Authentication failed — check BROKER_KEY"}
    else:
        return {"status": "error", "error": body.get("error", f"HTTP {code}")}


def action_clear(params, caller):
    """DELETE /inbox?for=<caller> — очистить inbox caller'а."""
    path = "/inbox"
    if caller:
        path = f"/inbox?for={caller}"

    code, body = _request("DELETE", path)

    if code == 200:
        deleted = body.get("deleted", 0)
        return {"status": "ok", "deleted": deleted, "message": f"Cleared {deleted} messages"}
    elif code == 403:
        return {"status": "error", "error": "Authentication failed — check BROKER_KEY"}
    else:
        return {"status": "error", "error": body.get("error", f"HTTP {code}")}


def action_list(params, caller):
    """GET /health — показать доступные инстансы (без auth)."""
    code, body = _request("GET", "/health", auth=False)

    if code == 200:
        instances = body.get("instances", [])
        return {
            "status": "ok",
            "instances": instances,
            "count": len(instances),
            "message": f"Available instances: {', '.join(instances)}" if instances else "No instances registered",
        }
    else:
        return {"status": "error", "error": body.get("error", f"HTTP {code}")}


ACTIONS = {
    "send": action_send,
    "inbox": action_inbox,
    "clear": action_clear,
    "list": action_list,
}


def main():
    raw = sys.stdin.read()
    try:
        params = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as e:
        print(json.dumps({"status": "error", "error": f"Invalid JSON input: {e}"}))
        sys.exit(1)

    action = params.get("action", "").strip()
    if not action:
        print(json.dumps({"status": "error", "error": "Missing 'action' parameter. Use: send, inbox, clear, list"}))
        sys.exit(1)

    handler = ACTIONS.get(action)
    if not handler:
        print(json.dumps({"status": "error", "error": f"Unknown action: {action}. Use: send, inbox, clear, list"}))
        sys.exit(1)

    if action != "list" and not BROKER_KEY:
        print(json.dumps({"status": "error", "error": "BROKER_KEY not configured"}))
        sys.exit(1)

    # caller is passed by service-agent from the API request
    caller = params.get("caller", "").strip().lower() or None

    result = handler(params, caller)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
