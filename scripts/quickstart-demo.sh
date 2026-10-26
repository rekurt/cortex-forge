#!/usr/bin/env bash
# quickstart-demo.sh — 10-second live interactive demo of CortexForge Enterprise
# Runs a live local quota-proxy + mock Anthropic SSE upstream + message-broker
# with zero Docker or external API keys required.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
python3 "$ROOT/scripts/benchmark-1000-users.py" --users 50 --workers 16
