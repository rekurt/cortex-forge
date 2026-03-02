#!/usr/bin/env python3
"""
Service Agent — HTTP API для внутренних сервисов.

POST /v1/run     — выполнить скилл
GET  /v1/skills  — список доступных скиллов
GET  /v1/health  — healthcheck (без авторизации)
GET  /v1/usage   — текущее использование (из /data/usage.db)

Auth: Authorization: Bearer <SERVICE_API_KEY>

Python stdlib only. No pip.
"""

import os
import re
import hmac
import hashlib
import json
import time
import sqlite3
import logging
import threading
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone
from pathlib import Path

# ── Configuration ─────────────────────────────────────────────────────────────

SERVICE_PORT         = int(os.environ.get("SERVICE_PORT", "8090"))
SERVICE_API_KEY      = os.environ.get("SERVICE_API_KEY", "")
_service_api_hash    = hashlib.sha256(SERVICE_API_KEY.encode()).hexdigest() if SERVICE_API_KEY else ""
SKILL_TIMEOUT        = int(os.environ.get("SKILL_TIMEOUT", "120"))
MAX_CONCURRENT_TASKS = int(os.environ.get("MAX_CONCURRENT_TASKS", "5"))
USAGE_DB             = os.environ.get("USAGE_DB", "/data/usage.db")

SKILLS_DIR = Path(os.environ.get("SKILLS_DIR", "/app/skills"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("service-agent")

# Semaphore to cap concurrent skill executions
_task_semaphore = threading.Semaphore(MAX_CONCURRENT_TASKS)

# Explicit skill whitelist — populated at startup and on reload.
# run_skill() validates skill_id against this set before any exec call.
_ALLOWED_SKILLS: set = set()
_skills_lock = threading.Lock()


# ── SQLite usage tracking ─────────────────────────────────────────────────────

def init_db():
    os.makedirs(os.path.dirname(USAGE_DB) or ".", exist_ok=True)
    conn = sqlite3.connect(USAGE_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS calls (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT    NOT NULL,
            caller      TEXT    NOT NULL,
            skill       TEXT    NOT NULL,
            params_json TEXT    NOT NULL,
            success     INTEGER NOT NULL,
            duration_ms INTEGER NOT NULL,
            output_len  INTEGER NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def record_call(caller: str, skill: str, params: dict,
                success: bool, duration_ms: int, output_len: int):
    conn = sqlite3.connect(USAGE_DB)
    try:
        conn.execute(
            "INSERT INTO calls (timestamp, caller, skill, params_json, success, duration_ms, output_len) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                datetime.now(timezone.utc).isoformat(),
                caller,
                skill,
                json.dumps(params, ensure_ascii=False),
                1 if success else 0,
                duration_ms,
                output_len,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_usage_stats() -> dict:
    conn = sqlite3.connect(USAGE_DB)
    try:
        rows = conn.execute("""
            SELECT skill,
                   COUNT(*)                     AS total_calls,
                   SUM(success)                 AS successful,
                   AVG(duration_ms)             AS avg_duration_ms,
                   SUM(output_len)              AS total_output_bytes,
                   MAX(timestamp)               AS last_called
            FROM calls
            GROUP BY skill
        """).fetchall()
        return {
            "by_skill": [
                {
                    "skill":              r[0],
                    "total_calls":        r[1],
                    "successful":         r[2],
                    "avg_duration_ms":    round(r[3] or 0, 1),
                    "total_output_bytes": r[4],
                    "last_called":        r[5],
                }
                for r in rows
            ]
        }
    finally:
        conn.close()


# ── Skills discovery ──────────────────────────────────────────────────────────

def load_skills() -> dict:
    """Scan skills/ directory. Each subdir with run.py or run.sh is a skill."""
    skills = {}
    if not SKILLS_DIR.exists():
        return skills

    for skill_dir in SKILLS_DIR.iterdir():
        if not skill_dir.is_dir():
            continue
        skill_id = skill_dir.name

        # Prefer skills.json manifest
        manifest_path = skill_dir / "skills.json"
        if manifest_path.exists():
            try:
                with open(manifest_path) as f:
                    manifest = json.load(f)
                skills[skill_id] = manifest
                continue
            except Exception as e:
                log.warning(f"Failed to parse {manifest_path}: {e}")

        # Fallback: auto-detect runner
        runner = None
        if (skill_dir / "run.py").exists():
            runner = "run.py"
        elif (skill_dir / "run.sh").exists():
            runner = "run.sh"

        if runner:
            skills[skill_id] = {
                "id":          skill_id,
                "name":        skill_id,
                "description": f"Skill {skill_id}",
                "runner":      runner,
            }

    return skills


def reload_skills() -> set:
    """
    Refresh the in-memory allowed skills whitelist from SKILLS_DIR.
    Thread-safe. Called at startup and optionally on /v1/skills requests.
    Returns the new whitelist set.
    """
    global _ALLOWED_SKILLS
    discovered = set(load_skills().keys())
    with _skills_lock:
        _ALLOWED_SKILLS = discovered
    log.info("Allowed skills whitelist refreshed: %s",
             ", ".join(sorted(discovered)) or "(empty)")
    return discovered


def find_runner(skill_id: str) -> tuple:
    """Return (cmd_list, timeout) for the skill, or raise ValueError."""
    skill_dir = SKILLS_DIR / skill_id
    if not skill_dir.exists():
        raise ValueError(f"Skill '{skill_id}' not found")

    # Check manifest for custom timeout
    timeout = SKILL_TIMEOUT
    manifest_path = skill_dir / "skills.json"
    if manifest_path.exists():
        try:
            with open(manifest_path) as f:
                m = json.load(f)
            timeout = m.get("timeout", SKILL_TIMEOUT)
        except Exception:
            pass

    if (skill_dir / "run.py").exists():
        return (["python3", str(skill_dir / "run.py")], timeout)
    if (skill_dir / "run.sh").exists():
        return (["bash", str(skill_dir / "run.sh")], timeout)

    raise ValueError(f"Skill '{skill_id}' has no run.py or run.sh")


# ── Skill environment isolation ───────────────────────────────────────────────

# Variables always passed to skills — safe, non-secret system vars.
_ENV_WHITELIST = frozenset({
    "PATH", "HOME", "TMPDIR", "TEMP", "TMP",
    "LANG", "LC_ALL", "LC_CTYPE", "LC_MESSAGES",
    "USER", "LOGNAME",
    "PYTHONIOENCODING",  # предотвращает UnicodeEncodeError при выводе не-ASCII символов
})


def build_skill_env(skill_id: str) -> dict:
    """
    Return a sanitised environment dict for skill execution.

    Always includes _ENV_WHITELIST vars (if present in os.environ).
    Additional vars can be declared in the skill's skills.json as:
      "env_vars": ["DADATA_API_KEY", "SOME_TOKEN"]
    Only vars listed there will be forwarded from the host environment.
    """
    env: dict = {}

    # 1. Safe system variables
    for key in _ENV_WHITELIST:
        if key in os.environ:
            env[key] = os.environ[key]

    # 2. Skill-declared variables from manifest
    manifest_path = SKILLS_DIR / skill_id / "skills.json"
    if manifest_path.exists():
        try:
            with open(manifest_path) as f:
                manifest = json.load(f)
            for var in manifest.get("env_vars", []):
                if isinstance(var, str) and var in os.environ:
                    env[var] = os.environ[var]
        except Exception as e:
            log.warning("Failed to read env_vars from %s: %s", manifest_path, e)

    return env


# ── Skill execution ───────────────────────────────────────────────────────────

def run_skill(skill_id: str, caller: str, params: dict) -> dict:
    """
    Execute a skill synchronously.
    Sends params as JSON via stdin.
    Returns {"status": "ok"|"error", "skill": ..., "result": ..., "duration_ms": ...}
    """
    start = time.time()

    # ── Explicit whitelist check (defense-in-depth) ───────────────────────────
    # skill_id must be validated against _ALLOWED_SKILLS before any exec call,
    # even if the HTTP handler already validated it (protects direct callers).
    with _skills_lock:
        allowed = frozenset(_ALLOWED_SKILLS)
    if skill_id not in allowed:
        log.warning("Blocked skill execution — '%s' not in ALLOWED_SKILLS (caller=%s)",
                    skill_id, caller)
        return {
            "status":      "error",
            "skill":       skill_id,
            "error":       f"Skill '{skill_id}' is not in the allowed skills whitelist",
            "duration_ms": 0,
        }

    acquired = _task_semaphore.acquire(timeout=5)
    if not acquired:
        return {
            "status":      "error",
            "skill":       skill_id,
            "error":       "Too many concurrent tasks. Retry later.",
            "duration_ms": 0,
        }

    try:
        cmd, timeout = find_runner(skill_id)
    except ValueError as e:
        _task_semaphore.release()
        return {
            "status":      "error",
            "skill":       skill_id,
            "error":       str(e),
            "duration_ms": 0,
        }

    params_json = json.dumps(params, ensure_ascii=False)

    # skill_id validated: not in allowed → returned at line 268; allowlist enforced
    try:
        proc = subprocess.run(
            cmd,
            input=params_json,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=build_skill_env(skill_id),
        )
        duration_ms = int((time.time() - start) * 1000)

        if proc.returncode == 0:
            try:
                result = json.loads(proc.stdout)
            except json.JSONDecodeError:
                result = {"output": proc.stdout}

            record_call(caller, skill_id, params, True, duration_ms, len(proc.stdout))
            return {
                "status":      "ok",
                "skill":       skill_id,
                "result":      result,
                "duration_ms": duration_ms,
            }
        else:
            err_msg = (proc.stderr or proc.stdout or "")[:500]
            record_call(caller, skill_id, params, False, duration_ms, 0)
            return {
                "status":      "error",
                "skill":       skill_id,
                "error":       err_msg,
                "duration_ms": duration_ms,
            }

    except subprocess.TimeoutExpired:
        duration_ms = int((time.time() - start) * 1000)
        record_call(caller, skill_id, params, False, duration_ms, 0)
        return {
            "status":      "error",
            "skill":       skill_id,
            "error":       f"Skill timed out after {timeout}s",
            "duration_ms": duration_ms,
        }
    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        record_call(caller, skill_id, params, False, duration_ms, 0)
        return {
            "status":      "error",
            "skill":       skill_id,
            "error":       str(e),
            "duration_ms": duration_ms,
        }
    finally:
        _task_semaphore.release()


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def require_auth(handler) -> bool:
    auth = handler.headers.get("Authorization", "")
    if not SERVICE_API_KEY:
        return True  # auth disabled
    if auth.startswith("Bearer ") and hmac.compare_digest(
        hashlib.sha256(auth[7:].encode()).hexdigest(),
        _service_api_hash,
    ):
        return True
    body = b'{"status":"error","error":"unauthorized"}'
    handler.send_response(401)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)
    return False


def send_json(handler, data: dict, status: int = 200):
    body = json.dumps(data, ensure_ascii=False, indent=2).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def read_body(handler) -> bytes:
    length = int(handler.headers.get("Content-Length", "0"))
    return handler.rfile.read(length) if length else b""


# ── HTTP Handler ──────────────────────────────────────────────────────────────

class ServiceHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        log.debug(f"HTTP {fmt % args}")

    # ── GET ──────────────────────────────────────────────────────────────────

    def do_GET(self):
        path = self.path.split("?")[0]

        if path == "/v1/health":
            send_json(self, {
                "status":         "ok",
                "skills_dir":     str(SKILLS_DIR),
                "max_concurrent": MAX_CONCURRENT_TASKS,
            })
            return

        if not require_auth(self):
            return

        if path == "/v1/skills":
            skills = load_skills()
            reload_skills()   # keep _ALLOWED_SKILLS in sync after any fs changes
            send_json(self, {"skills": list(skills.values()), "count": len(skills)})

        elif path == "/v1/usage":
            send_json(self, get_usage_stats())

        else:
            send_json(self, {"status": "error", "error": "not found"}, 404)

    # ── POST ─────────────────────────────────────────────────────────────────

    def do_POST(self):
        path = self.path.split("?")[0]

        if not require_auth(self):
            return

        if path == "/v1/run":
            raw = read_body(self)
            try:
                body = json.loads(raw)
            except json.JSONDecodeError as e:
                send_json(self, {"status": "error", "error": f"Invalid JSON: {e}"}, 400)
                return

            skill_id = body.get("skill", "").strip()
            caller   = body.get("caller", "unknown")
            params   = body.get("params", {})

            if not skill_id:
                send_json(self, {"status": "error", "error": "Missing 'skill' field"}, 400)
                return

            # Validate skill_id: alphanumeric + dashes/underscores only, no path traversal
            if not re.match(r'^[a-z][a-z0-9_-]{0,63}$', skill_id):
                send_json(self, {"status": "error", "error": "Invalid skill name"}, 400)
                return

            # Whitelist check: skill must be in ALLOWED_SKILLS (populated at startup)
            with _skills_lock:
                allowed_now = frozenset(_ALLOWED_SKILLS)
            if skill_id not in allowed_now:
                send_json(self, {"status": "error", "error": f"Unknown skill: {skill_id}"}, 404)
                return

            log.info(f"Run skill={skill_id} caller={caller}")
            result = run_skill(skill_id, caller, params)
            status_code = 200 if result["status"] == "ok" else 500
            send_json(self, result, status_code)

        else:
            send_json(self, {"status": "error", "error": "not found"}, 404)


# ── Entry Point ───────────────────────────────────────────────────────────────

def main():
    log.info(f"Service Agent starting — port={SERVICE_PORT} max_concurrent={MAX_CONCURRENT_TASKS}")
    log.info(f"Skills dir: {SKILLS_DIR}")
    init_db()

    skills_set = reload_skills()   # populates _ALLOWED_SKILLS whitelist
    log.info(f"Loaded {len(skills_set)} skill(s): {', '.join(sorted(skills_set)) or 'none'}")

    server = HTTPServer(("0.0.0.0", SERVICE_PORT), ServiceHandler)
    log.info(f"Listening on 0.0.0.0:{SERVICE_PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Shutting down")


if __name__ == "__main__":
    main()
