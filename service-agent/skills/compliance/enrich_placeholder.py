#!/usr/bin/env python3
"""
enrich.py placeholder.

The real enrich.py is NOT stored in this repo — it's large and updated
independently of the service-agent image.

To wire it up, either:

  Option A — volume mount (recommended, no rebuild needed):
    In docker-compose.yml the assistant-service service already mounts:
      ${ENRICH_PY_PATH:-./service-agent/skills/compliance/enrich_placeholder.py}:/app/skills/compliance/enrich.py:ro

    Set ENRICH_PY_PATH in .env to the actual path:
      ENRICH_PY_PATH=/home/user/.openclaw/workspace/skills/compliance-risk/scripts/enrich.py

  Option B — copy before build:
    cp ~/workspace/skills/compliance-risk/scripts/enrich.py \\
       service-agent/skills/compliance/enrich.py
    docker-compose build assistant-service

This file is used as the default mount target when ENRICH_PY_PATH is not set,
so that the service starts without errors (it will return a descriptive error
when the compliance skill is actually called).
"""

import sys
import json

if __name__ == "__main__":
    print(json.dumps({
        "error": (
            "enrich.py placeholder. Set ENRICH_PY_PATH in .env to point to the real "
            "enrich.py, then restart the assistant-service container."
        )
    }))
    sys.exit(1)
