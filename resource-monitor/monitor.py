#!/usr/bin/env python3
"""
CortexForge Monitor — resource metrics & alerting (HTTP + polling).

Polls Docker Stats API + disk usage + quota-proxy every MONITOR_INTERVAL seconds.
Stores metrics in SQLite, sends alerts to message-broker.
Exposes HTTP API on MONITOR_PORT (default 9091).

Python stdlib only. No pip.
"""

from __future__ import annotations

import os
import sys
import json
import time
import socket
import sqlite3
import shutil
import threading
import concurrent.futures
import hmac
import hashlib
import logging
from http.server import HTTPServer, ThreadingHTTPServer, BaseHTTPRequestHandler
from http.client import HTTPConnection
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs

# ── Configuration ────────────────────────────────────────────────────────────

MONITOR_PORT     = int(os.environ.get("MONITOR_PORT", "9091"))
MONITOR_INTERVAL = int(os.environ.get("MONITOR_INTERVAL", "60"))
MONITOR_DB       = os.environ.get("MONITOR_DB", "/data/metrics.db")
MONITOR_ADMIN_TOKEN = os.environ.get("MONITOR_ADMIN_TOKEN", "")
_admin_hash         = hashlib.sha256(MONITOR_ADMIN_TOKEN.encode()).hexdigest() if MONITOR_ADMIN_TOKEN else ""

QUOTA_ADMIN_TOKEN = os.environ.get("QUOTA_ADMIN_TOKEN", "")
QUOTA_PROXY_URL   = os.environ.get("QUOTA_PROXY_URL", "http://quota-proxy:9090")
BROKER_URL        = os.environ.get("BROKER_URL", "http://message-broker:8080")
BROKER_KEY_MONITOR = os.environ.get("BROKER_KEY_MONITOR", "")
if not BROKER_KEY_MONITOR:
    # Не используем MONITOR_ADMIN_TOKEN как fallback — broker его не распознает.
    # Алерты в broker будут отключены до задания BROKER_KEY_MONITOR в .env.
    print("[monitor] WARNING: BROKER_KEY_MONITOR not set — broker alerts disabled", file=sys.stderr)

ALERT_CPU_PCT   = float(os.environ.get("ALERT_CPU_PCT", "80"))
ALERT_RAM_PCT   = float(os.environ.get("ALERT_RAM_PCT", "85"))
ALERT_DISK_PCT  = float(os.environ.get("ALERT_DISK_PCT", "90"))
ALERT_QUOTA_PCT = float(os.environ.get("ALERT_QUOTA_PCT", "80"))

DOCKER_SOCK = "/var/run/docker.sock"
ALERT_COOLDOWN = 3600  # 1 hour in seconds

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("monitor")

# ── UTF-8 safe HTTP helper ───────────────────────────────────────────────────

def _http(method: str, url: str, body: bytes = None, headers: dict = None) -> bytes:
    """Make HTTP request using http.client directly — avoids urllib latin-1 issues."""
    p = urlparse(url)
    host, port = p.hostname, p.port or (443 if p.scheme == "https" else 80)
    path = p.path or "/"
    if p.query:
        path += "?" + p.query
    conn = HTTPConnection(host, port, timeout=10)
    try:
        # HTTP headers must be latin-1 compatible — encode safely to avoid UnicodeEncodeError
        h = {k: str(v).encode("latin-1", errors="replace").decode("latin-1")
             for k, v in (headers or {}).items()}
        if body is not None:
            h.setdefault("Content-Length", str(len(body)))
        conn.request(method, path, body=body, headers=h)
        resp = conn.getresponse()
        return resp.read()
    finally:
        conn.close()


# ── Shared state (protected by lock) ─────────────────────────────────────────

_lock = threading.Lock()
_last_metrics = {}   # container_id -> metric dict
_last_disk    = {}   # {"used_pct": float, ...}
_last_quota   = {}   # instance -> quota info
_active_alerts = {}  # alert_key -> {"fired_at": ts, "message": str}


# ── Docker Stats via Unix Socket ──────────────────────────────────────────────

class UnixSocketHTTPConnection(HTTPConnection):
    """HTTPConnection over a Unix domain socket."""

    def __init__(self, sock_path):
        super().__init__("localhost")
        self.sock_path = sock_path

    def connect(self):
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(self.sock_path)
        self.sock = s


def docker_get(path: str) -> dict:
    """Make a GET request to Docker API via unix socket. Returns parsed JSON."""
    conn = UnixSocketHTTPConnection(DOCKER_SOCK)
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        raw = resp.read()
        return json.loads(raw)
    finally:
        conn.close()


def list_containers() -> list:
    """Return list of running containers: [{id, name}]."""
    try:
        containers = docker_get("/containers/json")
        result = []
        for c in containers:
            cid  = c.get("Id", "")[:12]
            name = (c.get("Names") or ["unknown"])[0].lstrip("/")
            result.append({"id": c.get("Id", ""), "short_id": cid, "name": name})
        return result
    except Exception as e:
        log.error(f"list_containers: Docker socket error ({DOCKER_SOCK}): {type(e).__name__}: {e}")
        return []


def get_container_stats(container_id: str) -> dict:
    """Fetch stats for one container (stream=false)."""
    path = f"/containers/{container_id}/stats?stream=false"
    return docker_get(path)


def parse_cpu_pct(stats: dict) -> float:
    """Calculate CPU % from Docker stats snapshot."""
    try:
        cpu_stats  = stats["cpu_stats"]
        precpu     = stats["precpu_stats"]

        cpu_delta  = (cpu_stats["cpu_usage"]["total_usage"]
                      - precpu["cpu_usage"]["total_usage"])
        sys_delta  = (cpu_stats.get("system_cpu_usage", 0)
                      - precpu.get("system_cpu_usage", 0))

        num_cpus   = cpu_stats.get("online_cpus") or len(
            cpu_stats["cpu_usage"].get("percpu_usage", [1])
        )

        if sys_delta > 0 and cpu_delta > 0:
            return (cpu_delta / sys_delta) * num_cpus * 100.0
        return 0.0
    except (KeyError, ZeroDivisionError):
        return 0.0


def parse_ram(stats: dict) -> tuple:
    """Return (ram_mb, ram_limit_mb)."""
    try:
        mem = stats["memory_stats"]
        usage = mem.get("usage", 0)
        # subtract cache (rss only)
        cache = mem.get("stats", {}).get("cache", 0)
        rss   = max(usage - cache, 0)
        limit = mem.get("limit", 0)
        return rss / 1024 / 1024, limit / 1024 / 1024
    except KeyError:
        return 0.0, 0.0


def parse_blkio(stats: dict) -> dict:
    """Return block I/O totals."""
    try:
        blkio = stats.get("blkio_stats", {})
        entries = blkio.get("io_service_bytes_recursive") or []
        read_b  = sum(e["value"] for e in entries if e.get("op") == "Read")
        write_b = sum(e["value"] for e in entries if e.get("op") == "Write")
        return {"read_mb": read_b / 1024 / 1024, "write_mb": write_b / 1024 / 1024}
    except Exception:
        return {"read_mb": 0.0, "write_mb": 0.0}


# ── Disk Usage ────────────────────────────────────────────────────────────────

def get_disk_usage() -> dict:
    try:
        usage = shutil.disk_usage("/")
        used_pct = usage.used / usage.total * 100
        return {
            "total_gb": usage.total / 1024**3,
            "used_gb":  usage.used  / 1024**3,
            "free_gb":  usage.free  / 1024**3,
            "used_pct": used_pct,
        }
    except Exception as e:
        log.warning(f"disk_usage failed: {e}")
        return {}


# ── Quota Proxy ───────────────────────────────────────────────────────────────

def get_quota_report() -> dict:
    try:
        raw = _http("GET", f"{QUOTA_PROXY_URL}/quota/report",
                    headers={"Authorization": f"Bearer {QUOTA_ADMIN_TOKEN}"})
        return json.loads(raw.decode("utf-8"))
    except Exception as e:
        log.warning(f"quota report failed: {e}")
        return {}


# ── SQLite ────────────────────────────────────────────────────────────────────

def _get_db_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(MONITOR_DB, timeout=10.0)
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def init_db():
    os.makedirs(os.path.dirname(MONITOR_DB) or ".", exist_ok=True)
    conn = _get_db_conn()
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA journal_size_limit=1048576")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS snapshots (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT    NOT NULL,
            container   TEXT    NOT NULL,
            cpu_pct     REAL    NOT NULL,
            ram_mb      REAL    NOT NULL,
            ram_limit_mb REAL   NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_container_ts ON snapshots (container, timestamp)")
    conn.commit()
    conn.close()


def write_snapshots(metrics: list):
    """Write a list of metric dicts to SQLite."""
    if not metrics:
        return
    conn = _get_db_conn()
    try:
        conn.executemany(
            "INSERT INTO snapshots (timestamp, container, cpu_pct, ram_mb, ram_limit_mb) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (
                    m["timestamp"],
                    m["name"],
                    m["cpu_pct"],
                    m["ram_mb"],
                    m["ram_limit_mb"],
                )
                for m in metrics
            ],
        )
        conn.commit()
    finally:
        conn.close()


# ── Alerts ────────────────────────────────────────────────────────────────────

def _extract_instance_from_key(key: str) -> str:
    """Extract instance or container name from alert key (e.g., 'cpu:corp-user-1' -> 'corp-user-1')."""
    if ":" in key:
        return key.split(":", 1)[1]
    return key


def send_alert(key: str, message: str):
    """Send alert to broker if cooldown has passed."""
    now = time.time()
    instance = _extract_instance_from_key(key)
    with _lock:
        last = _active_alerts.get(key, {}).get("fired_at", 0)
        if now - last < ALERT_COOLDOWN:
            return  # still in cooldown
        _active_alerts[key] = {
            "fired_at": now,
            "message":  message,
            "key":      key,
            "instance": instance,
        }

    log.warning(f"ALERT [{key}]: {message}")
    if not BROKER_KEY_MONITOR:
        return  # broker alerts disabled — no key configured
    try:
        body = json.dumps({
            "to":      "admin",
            "message": f"[ALERT {key}] {message}",
        }, ensure_ascii=False).encode("utf-8")
        _http("POST", f"{BROKER_URL}/send", body=body, headers={
            "Content-Type":  "application/json; charset=utf-8",
            "Authorization": f"Bearer {BROKER_KEY_MONITOR}",
        })
    except Exception as e:
        log.warning(f"Failed to send alert to broker: {e}")


def check_alerts(metrics: list, disk: dict, quota: dict):
    """Evaluate thresholds and fire alerts as needed."""
    # Cleanup expired entries to prevent unbounded memory growth
    now = time.time()
    with _lock:
        expired = [k for k, v in _active_alerts.items()
                   if now - v.get("fired_at", 0) > ALERT_COOLDOWN]
        for k in expired:
            del _active_alerts[k]

    for m in metrics:
        name = m["name"]

        # CPU alert
        if m["cpu_pct"] > ALERT_CPU_PCT:
            send_alert(
                f"cpu:{name}",
                f"Container {name}: CPU {m['cpu_pct']:.1f}% > {ALERT_CPU_PCT}%",
            )

        # RAM alert
        if m["ram_limit_mb"] > 0:
            ram_pct = m["ram_mb"] / m["ram_limit_mb"] * 100
            if ram_pct > ALERT_RAM_PCT:
                send_alert(
                    f"ram:{name}",
                    f"Container {name}: RAM {ram_pct:.1f}% ({m['ram_mb']:.0f}/{m['ram_limit_mb']:.0f} MB) > {ALERT_RAM_PCT}%",
                )

    # Disk alert
    if disk and disk.get("used_pct", 0) > ALERT_DISK_PCT:
        send_alert(
            "disk:host",
            f"Host disk: {disk['used_pct']:.1f}% used ({disk['used_gb']:.1f}/{disk['total_gb']:.1f} GB) > {ALERT_DISK_PCT}%",
        )

    # Quota alert — quota-proxy /quota/report returns {"month": ..., "usage": [...], "limits": {...}}
    for item in quota.get("usage", []):
        instance = item.get("instance", "")
        used  = item.get("total_tokens", 0)
        limit = item.get("limit", 0)
        if isinstance(limit, int) and limit > 0 and used / limit * 100 > ALERT_QUOTA_PCT:
            send_alert(
                f"quota:{instance}",
                f"Token quota [{instance}]: {used}/{limit} ({used/limit*100:.1f}%) > {ALERT_QUOTA_PCT}%",
            )


# ── Polling Loop ──────────────────────────────────────────────────────────────

def poll_once():
    """Collect all metrics, update state, write to DB, check alerts."""
    ts = datetime.now(timezone.utc).isoformat()
    metrics = []

    containers = list_containers()

    def _fetch_one(c: dict) -> dict | None:
        try:
            stats   = get_container_stats(c["id"])
            cpu_pct = parse_cpu_pct(stats)
            ram_mb, ram_limit_mb = parse_ram(stats)
            blkio   = parse_blkio(stats)

            mem_pct = (ram_mb / ram_limit_mb * 100.0) if ram_limit_mb > 0 else 0.0
            return {
                "timestamp":    ts,
                "id":           c["short_id"],
                "name":         c["name"],
                "cpu_pct":      round(cpu_pct, 2),
                "ram_mb":       round(ram_mb, 2),
                "ram_limit_mb": round(ram_limit_mb, 2),
                "mem_pct":      round(mem_pct, 2),
                "blkio":        blkio,
            }
        except Exception as e:
            log.warning(f"Stats for {c['name']} failed: {e}")
            return None

    if containers:
        max_workers = min(32, len(containers) or 1)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
            for m in pool.map(_fetch_one, containers):
                if m is not None:
                    metrics.append(m)

    disk  = get_disk_usage()
    quota = get_quota_report()

    with _lock:
        _last_metrics.clear()
        for m in metrics:
            _last_metrics[m["name"]] = m
        _last_disk.clear()
        _last_disk.update(disk)
        _last_quota.clear()
        _last_quota.update(quota)

    write_snapshots(metrics)
    check_alerts(metrics, disk, quota)

    disk_pct = disk.get('used_pct')
    disk_str = f"{disk_pct:.1f}%" if disk_pct is not None else "N/A"
    log.info(f"Poll done: {len(metrics)} containers, disk={disk_str}")


def polling_loop():
    while True:
        try:
            poll_once()
        except Exception as e:
            log.error(f"poll_once exception: {e}")
        time.sleep(MONITOR_INTERVAL)


# ── HTTP API ──────────────────────────────────────────────────────────────────

def require_auth(handler) -> bool:
    """Check Bearer token. Returns True if valid."""
    auth = handler.headers.get("Authorization", "")
    if not MONITOR_ADMIN_TOKEN:
        return True  # auth disabled (no token configured)
    if auth.startswith("Bearer ") and hmac.compare_digest(
        hashlib.sha256(auth[7:].encode()).hexdigest(),
        _admin_hash,
    ):
        return True
    handler.send_response(401)
    handler.send_header("Content-Type", "application/json")
    handler.end_headers()
    handler.wfile.write(b'{"error":"unauthorized"}')
    return False


def send_json(handler, data: dict, status: int = 200):
    body = json.dumps(data, ensure_ascii=False, indent=2).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _container_mem_pct(c: dict) -> float:
    """Compute or retrieve memory usage percentage for a container metric dict."""
    if "mem_pct" in c and c["mem_pct"] is not None:
        return float(c["mem_pct"])
    ram_mb = float(c.get("ram_mb", c.get("mem_mb", 0.0)) or 0.0)
    limit_mb = float(c.get("ram_limit_mb", c.get("mem_limit_mb", 0.0)) or 0.0)
    if limit_mb > 0:
        return round(ram_mb / limit_mb * 100.0, 2)
    return 0.0


def _is_container_unhealthy(c: dict) -> bool:
    """Determine if a container is unhealthy by status flag or resource threshold."""
    if c.get("healthy") is False or c.get("unhealthy") is True:
        return True
    if c.get("status") in ("unhealthy", "dead", "exited", "restarting"):
        return True
    if c.get("health") in ("unhealthy", "failing"):
        return True
    cpu_pct = float(c.get("cpu_pct", 0.0) or 0.0)
    mem_pct = _container_mem_pct(c)
    if cpu_pct > ALERT_CPU_PCT or mem_pct > ALERT_RAM_PCT:
        return True
    return False


def _alert_matches_instance(alert: dict, instance: str) -> bool:
    """Check whether an alert dictionary matches the requested instance filter."""
    target = instance.strip()
    if not target:
        return True
    candidates = {target, f"corp-{target}"}
    if target.startswith("corp-"):
        candidates.add(target[5:])

    alert_inst = str(alert.get("instance", "") or alert.get("container", ""))
    if alert_inst in candidates:
        return True

    key = str(alert.get("key", ""))
    if ":" in key and key.split(":", 1)[1] in candidates:
        return True
    if any(cand in key for cand in candidates):
        return True

    msg = str(alert.get("message", ""))
    if any(cand in msg for cand in candidates):
        return True
    return False


class MonitorHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        log.debug(f"HTTP {fmt % args}")

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        # /health — no auth required
        if path == "/health":
            send_json(self, {"status": "ok"})
            return

        if not require_auth(self):
            return

        if path == "/metrics":
            search_q   = (qs.get("search", [None])[0] or "").strip().lower()
            sort_by    = (qs.get("sort", [None])[0] or "").strip().lower()
            order_q    = (qs.get("order", [None])[0] or "").strip().lower()
            raw_limit  = qs.get("limit", [None])[0]
            raw_offset = qs.get("offset", ["0"])[0]

            try:
                limit_val  = int(raw_limit) if raw_limit is not None else None
                offset_val = max(0, int(raw_offset)) if raw_offset is not None else 0
            except ValueError:
                send_json(self, {"error": "invalid limit or offset"}, 400)
                return

            with _lock:
                raw_containers = [dict(c) for c in _last_metrics.values()]
                disk_copy  = dict(_last_disk)
                quota_copy = dict(_last_quota)

            # Ensure mem_pct is populated on each container entry
            for c in raw_containers:
                if "mem_pct" not in c:
                    c["mem_pct"] = _container_mem_pct(c)

            # Filter by substring in container name
            if search_q:
                filtered = [
                    c for c in raw_containers
                    if search_q in str(c.get("name", "")).lower()
                ]
            else:
                filtered = raw_containers

            # Compute summary across all matched containers (pre-pagination)
            total_containers = len(filtered)
            total_mem_mb = round(
                sum(float(c.get("ram_mb", c.get("mem_mb", 0.0)) or 0.0) for c in filtered),
                2,
            )
            avg_cpu_pct = (
                round(
                    sum(float(c.get("cpu_pct", 0.0) or 0.0) for c in filtered) / total_containers,
                    2,
                )
                if total_containers > 0
                else 0.0
            )
            unhealthy_count = sum(1 for c in filtered if _is_container_unhealthy(c))

            # Sort containers if requested
            if sort_by == "mem_pct":
                reverse = False if order_q == "asc" else True
                filtered.sort(key=lambda c: (_container_mem_pct(c), c.get("name", "")), reverse=reverse)
            elif sort_by == "cpu_pct":
                reverse = False if order_q == "asc" else True
                filtered.sort(key=lambda c: (float(c.get("cpu_pct", 0.0) or 0.0), c.get("name", "")), reverse=reverse)
            elif sort_by == "name":
                reverse = True if order_q == "desc" else False
                filtered.sort(key=lambda c: str(c.get("name", "")), reverse=reverse)

            # Apply pagination
            if limit_val is not None:
                safe_limit = max(1, limit_val)
                paged_containers = filtered[offset_val:offset_val + safe_limit]
            elif offset_val > 0:
                paged_containers = filtered[offset_val:]
            else:
                paged_containers = filtered

            payload = {
                "containers":       paged_containers,
                "total_containers": total_containers,
                "summary": {
                    "total_mem_mb":    total_mem_mb,
                    "avg_cpu_pct":     avg_cpu_pct,
                    "unhealthy_count": unhealthy_count,
                },
                "disk":             disk_copy,
                "quota":            quota_copy,
                "polled_at":        datetime.now(timezone.utc).isoformat(),
            }
            send_json(self, payload)

        elif path.startswith("/metrics/"):
            name = path[len("/metrics/"):]
            with _lock:
                m = _last_metrics.get(name)
            if m is None:
                send_json(self, {"error": f"container '{name}' not found"}, 404)
            else:
                send_json(self, m)

        elif path in ("/alerts", "/alerts/active"):
            instance_filter = (qs.get("instance", [None])[0] or "").strip()
            raw_limit       = qs.get("limit", [None])[0]
            raw_offset      = qs.get("offset", ["0"])[0]

            try:
                limit_val  = int(raw_limit) if raw_limit is not None else None
                offset_val = max(0, int(raw_offset)) if raw_offset is not None else 0
            except ValueError:
                send_json(self, {"error": "invalid limit or offset"}, 400)
                return

            with _lock:
                all_alerts = [dict(a) for a in _active_alerts.values()]

            if instance_filter:
                filtered_alerts = [
                    a for a in all_alerts
                    if _alert_matches_instance(a, instance_filter)
                ]
            else:
                filtered_alerts = all_alerts

            total_alerts = len(filtered_alerts)
            if limit_val is not None:
                safe_limit = max(1, limit_val)
                paged_alerts = filtered_alerts[offset_val:offset_val + safe_limit]
            elif offset_val > 0:
                paged_alerts = filtered_alerts[offset_val:]
            else:
                paged_alerts = filtered_alerts

            send_json(self, {
                "alerts": paged_alerts,
                "count":  len(paged_alerts),
                "total":  total_alerts,
            })

        else:
            send_json(self, {"error": "not found"}, 404)


# ── Entry Point ───────────────────────────────────────────────────────────────

def main():
    log.info(f"Resource Monitor starting — port={MONITOR_PORT} interval={MONITOR_INTERVAL}s")
    init_db()

    # Start background polling thread
    t = threading.Thread(target=polling_loop, daemon=True, name="poller")
    t.start()

    server = ThreadingHTTPServer(("0.0.0.0", MONITOR_PORT), MonitorHandler)
    log.info(f"HTTP API listening on 0.0.0.0:{MONITOR_PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Shutting down")


if __name__ == "__main__":
    main()
