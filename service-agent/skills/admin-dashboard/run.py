#!/usr/bin/env python3
"""
Admin Dashboard — единый центр управления CortexForge.

Skill для service-agent. Читает JSON из stdin, пишет JSON в stdout.
Агрегирует данные из quota-proxy, resource-monitor и broker.

Actions:
  overview    — сводка: квоты + метрики + алерты + broker health
  instances   — список инстансов с квотами и статусами
  set-limit   — изменить лимит токенов для инстанса
  reset-quota — сбросить счётчик токенов для инстанса
  help        — полный справочник по API, ключам, сетям, ошибкам

Python stdlib only. No pip.
"""

import json
import os
import sys
import urllib.request
import urllib.error

QUOTA_PROXY_URL = os.environ.get("QUOTA_PROXY_URL", "http://quota-proxy:9090")
QUOTA_ADMIN_TOKEN = os.environ.get("QUOTA_ADMIN_TOKEN", "")
MONITOR_URL = os.environ.get("MONITOR_URL", "http://resource-monitor:9091")
MONITOR_ADMIN_TOKEN = os.environ.get("MONITOR_ADMIN_TOKEN", "")
BROKER_URL = os.environ.get("BROKER_URL", "http://message-broker:8080")

TIMEOUT = 10  # seconds for HTTP requests

KNOWLEDGE_PATH = os.path.join(os.path.dirname(__file__), "KNOWLEDGE.md")


def _request(method, url, data=None, headers=None):
    """Make HTTP request. Returns (status_code, parsed_json)."""
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)

    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=hdrs, method=method)

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


def _admin_headers():
    """Headers with admin auth for quota-proxy."""
    return {"Authorization": f"Bearer {QUOTA_ADMIN_TOKEN}"}


def _fetch_quota_report():
    """GET /quota/report from quota-proxy."""
    code, body = _request(
        "GET",
        f"{QUOTA_PROXY_URL}/quota/report",
        headers=_admin_headers(),
    )
    if code == 200:
        return body
    return {"error": f"quota-proxy HTTP {code}", "detail": body}


def _fetch_quota_health():
    """GET /quota/health from quota-proxy (no auth needed)."""
    code, body = _request("GET", f"{QUOTA_PROXY_URL}/quota/health")
    if code == 200:
        return body
    return {"error": f"quota-proxy health HTTP {code}"}


def _monitor_headers():
    """Headers with auth for resource-monitor."""
    if MONITOR_ADMIN_TOKEN:
        return {"Authorization": f"Bearer {MONITOR_ADMIN_TOKEN}"}
    return {}


def _fetch_monitor_metrics():
    """GET /metrics from resource-monitor."""
    code, body = _request("GET", f"{MONITOR_URL}/metrics", headers=_monitor_headers())
    if code == 200:
        return body
    return {"error": f"monitor HTTP {code}", "detail": body}


def _fetch_monitor_alerts():
    """GET /alerts/active from resource-monitor."""
    code, body = _request("GET", f"{MONITOR_URL}/alerts/active", headers=_monitor_headers())
    if code == 200:
        return body
    return {"error": f"monitor alerts HTTP {code}", "detail": body}


def _fetch_broker_health():
    """GET /health from broker (no auth needed)."""
    code, body = _request("GET", f"{BROKER_URL}/health")
    if code == 200:
        return body
    return {"error": f"broker HTTP {code}", "detail": body}


def action_overview(params):
    """Aggregate overview: quota + metrics + alerts + broker health."""
    quota_report = _fetch_quota_report()
    monitor_metrics = _fetch_monitor_metrics()
    monitor_alerts = _fetch_monitor_alerts()
    broker_health = _fetch_broker_health()

    alert_count = monitor_alerts.get("count", 0) if isinstance(monitor_alerts, dict) else 0

    result = {
        "status": "ok",
        "quota": quota_report,
        "metrics": monitor_metrics,
        "alerts": monitor_alerts,
        "broker": broker_health,
        "summary": {
            "quota_instances": len(quota_report.get("usage", [])),
            "active_alerts": alert_count,
            "broker_instances": len(broker_health.get("instances", [])),
        },
        "hints": [
            "Изменить лимит: admin-dashboard action=set-limit name=<имя> limit=<число>",
            "Сбросить квоту: admin-dashboard action=reset-quota name=<имя>",
            "Список инстансов: admin-dashboard action=instances",
            "Справочник: admin-dashboard action=help",
        ],
    }
    return result


def action_instances(params):
    """List instances with quotas, usage, and statuses."""
    quota_health = _fetch_quota_health()
    quota_report = _fetch_quota_report()
    broker_health = _fetch_broker_health()
    monitor_metrics = _fetch_monitor_metrics()

    instances = {}

    # From quota-proxy health
    for name in quota_health.get("instances", []):
        instances.setdefault(name, {})["quota_registered"] = True
        limit_info = quota_health.get("limits", {}).get(name, {})
        if limit_info:
            instances[name]["limit"] = limit_info.get("limit")
            instances[name]["limit_updated_at"] = limit_info.get("updated_at")

    # From quota report
    for item in quota_report.get("usage", []):
        name = item.get("instance", "")
        if name:
            instances.setdefault(name, {})["usage"] = {
                "total_tokens": item.get("total_tokens", 0),
                "input_tokens": item.get("input_tokens", 0),
                "output_tokens": item.get("output_tokens", 0),
                "requests": item.get("requests", 0),
                "used_pct": item.get("used_pct", 0),
                "status": item.get("status", ""),
            }

    # From broker health
    for name in broker_health.get("instances", []):
        instances.setdefault(name, {})["broker_registered"] = True
    msg_counts = broker_health.get("message_counts", {})
    for name, count in msg_counts.items():
        instances.setdefault(name, {})["pending_messages"] = count

    # From monitor metrics
    containers = monitor_metrics.get("containers", []) if isinstance(monitor_metrics, dict) else []
    for c in containers:
        cname = c.get("name", "")
        # Match corp-<name> container to instance name
        if cname.startswith("corp-"):
            inst_name = cname[5:]  # strip "corp-"
            if inst_name in instances:
                instances[inst_name]["container"] = {
                    "cpu_pct": c.get("cpu_pct", 0),
                    "ram_mb": c.get("ram_mb", 0),
                    "ram_limit_mb": c.get("ram_limit_mb", 0),
                }

    return {
        "status": "ok",
        "instances": instances,
        "count": len(instances),
        "hints": [
            "Изменить лимит: admin-dashboard action=set-limit name=<имя> limit=<число>",
            "Сбросить квоту: admin-dashboard action=reset-quota name=<имя>",
        ],
    }


def action_set_limit(params):
    """POST /quota/set-limit on quota-proxy."""
    name = params.get("name", "").strip().lower()
    limit = params.get("limit")

    if not name:
        return {"status": "error", "error": "Missing 'name' parameter"}
    if limit is None:
        return {"status": "error", "error": "Missing 'limit' parameter"}
    try:
        limit = int(limit)
    except (ValueError, TypeError):
        return {"status": "error", "error": "'limit' must be an integer"}

    code, body = _request(
        "POST",
        f"{QUOTA_PROXY_URL}/quota/set-limit",
        data={"instance": name, "limit": limit},
        headers=_admin_headers(),
    )

    if code == 200:
        current_usage = body.get("current_usage", 0)
        return {
            "status": "ok",
            "message": f"Лимит {name} установлен: {limit:,} токенов/мес",
            "instance": name,
            "new_limit": limit,
            "current_usage": current_usage,
            "hint": f"Текущее использование: {current_usage:,} токенов",
        }
    elif code == 403:
        return {"status": "error", "error": "Authentication failed — check QUOTA_ADMIN_TOKEN"}
    elif code == 429:
        return {"status": "error", "error": "Rate limit exceeded"}
    else:
        return {"status": "error", "error": body.get("error", f"HTTP {code}")}


def action_reset_quota(params):
    """POST /quota/reset on quota-proxy."""
    name = params.get("name", "").strip().lower()

    if not name:
        return {"status": "error", "error": "Missing 'name' parameter"}

    code, body = _request(
        "POST",
        f"{QUOTA_PROXY_URL}/quota/reset",
        data={"instance": name},
        headers=_admin_headers(),
    )

    if code == 200:
        return {
            "status": "ok",
            "message": f"Квота {name} сброшена",
            "instance": name,
            "warning": "Счётчик токенов обнулён. Это действие необратимо.",
        }
    elif code == 403:
        return {"status": "error", "error": "Authentication failed — check QUOTA_ADMIN_TOKEN"}
    elif code == 429:
        return {"status": "error", "error": "Rate limit exceeded"}
    else:
        return {"status": "error", "error": body.get("error", f"HTTP {code}")}


def action_help(params):
    """Return comprehensive help from KNOWLEDGE.md."""
    try:
        with open(KNOWLEDGE_PATH, "r", encoding="utf-8") as f:
            knowledge = f.read()
    except FileNotFoundError:
        knowledge = "(KNOWLEDGE.md not found)"

    return {
        "status": "ok",
        "knowledge": knowledge,
        "actions": {
            "overview": "Сводка: квоты + метрики + алерты + broker",
            "instances": "Список инстансов с квотами и статусами",
            "set-limit": "Изменить лимит: params {name, limit}",
            "reset-quota": "Сбросить квоту: params {name}",
            "help": "Этот справочник",
        },
    }


ACTIONS = {
    "overview": action_overview,
    "instances": action_instances,
    "set-limit": action_set_limit,
    "reset-quota": action_reset_quota,
    "help": action_help,
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
        print(json.dumps({
            "status": "error",
            "error": "Missing 'action' parameter. Use: overview, instances, set-limit, reset-quota, help",
        }))
        sys.exit(1)

    handler = ACTIONS.get(action)
    if not handler:
        print(json.dumps({
            "status": "error",
            "error": f"Unknown action: {action}. Use: overview, instances, set-limit, reset-quota, help",
        }))
        sys.exit(1)

    if not QUOTA_ADMIN_TOKEN and action in ("overview", "instances", "set-limit", "reset-quota"):
        print(json.dumps({"status": "error", "error": "QUOTA_ADMIN_TOKEN not configured"}))
        sys.exit(1)

    result = handler(params)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
