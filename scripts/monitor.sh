#!/usr/bin/env bash
# Resource Monitor admin CLI
# Usage: bash scripts/monitor.sh [ACTION]
# Actions: metrics (default), alerts/active
# Env: MONITOR_URL (default http://localhost:9091), MONITOR_ADMIN_TOKEN

set -euo pipefail

ACTION="${1:-metrics}"
MONITOR_URL="${MONITOR_URL:-http://localhost:9091}"
TOKEN="${MONITOR_ADMIN_TOKEN:-}"

if [ -z "$TOKEN" ]; then
  echo "❌ MONITOR_ADMIN_TOKEN is not set" >&2
  exit 1
fi

curl -sf \
  -H "Authorization: Bearer $TOKEN" \
  "${MONITOR_URL}/${ACTION}" \
| python3 -m json.tool
