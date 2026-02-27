#!/usr/bin/env python3
"""
Compliance skill runner.

Reads JSON from stdin:
  {"inn": "7707083893", "mode": "full|short"}

Calls enrich.py (mounted at /app/skills/compliance/enrich.py) and
returns its JSON output on stdout.
"""

import sys
import json
import subprocess
import os


def main():
    try:
        raw = sys.stdin.read()
        params = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid JSON params: {e}"}))
        sys.exit(1)

    inn  = str(params.get("inn", "")).strip()
    mode = params.get("mode", "full")

    if not inn:
        print(json.dumps({"error": "Missing required param: inn"}))
        sys.exit(1)

    if mode not in ("full", "short"):
        print(json.dumps({"error": f"Invalid mode '{mode}'. Must be 'full' or 'short'"}))
        sys.exit(1)

    enrich_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "enrich.py")

    if not os.path.exists(enrich_path):
        print(json.dumps({
            "error": (
                "enrich.py not found. Mount it via docker-compose volume: "
            )
        }))
        sys.exit(1)

    cmd = ["python3", enrich_path, inn, "--json"]
    if mode == "short":
        cmd.append("--short")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=150,
            env={**os.environ},
        )

        if result.returncode == 0:
            # Validate output is JSON before passing through
            try:
                parsed = json.loads(result.stdout)
                print(json.dumps(parsed, ensure_ascii=False))
            except json.JSONDecodeError:
                # enrich.py returned non-JSON — wrap it
                print(json.dumps({"raw_output": result.stdout}))
        else:
            err = (result.stderr or result.stdout or "enrich.py failed")[:500]
            print(json.dumps({"error": err}))
            sys.exit(1)

    except subprocess.TimeoutExpired:
        print(json.dumps({"error": "enrich.py timed out after 150s"}))
        sys.exit(1)
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
