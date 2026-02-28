#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="/opt/cortex-forge/.env"
LOG_FILE="/opt/cortex-forge/logs/token-refresh.log"
mkdir -p "$(dirname "$LOG_FILE")"

log() { echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] $*" | tee -a "$LOG_FILE"; }

REFRESH_TOKEN=$(grep '^ANTHROPIC_REFRESH_TOKEN=' "$ENV_FILE" | cut -d= -f2-)

if [ -z "$REFRESH_TOKEN" ]; then
  log "ERROR: ANTHROPIC_REFRESH_TOKEN не найден в .env"
  exit 1
fi

log "Обновляем Anthropic OAuth token..."

RESPONSE=$(curl -s -X POST "https://claude.ai/api/auth/oauth/token" \
  -H "Content-Type: application/json" \
  -d "{\"grant_type\":\"refresh_token\",\"refresh_token\":\"${REFRESH_TOKEN}\"}" \
  --max-time 30)

NEW_ACCESS_TOKEN=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['access_token'])" 2>/dev/null || true)
NEW_REFRESH_TOKEN=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('refresh_token',''))" 2>/dev/null || true)
EXPIRES_AT=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('expires_at', d.get('expires_in','')))" 2>/dev/null || true)

if [ -z "$NEW_ACCESS_TOKEN" ]; then
  log "ERROR: не удалось получить новый токен. Ответ: $RESPONSE"
  exit 1
fi

log "Получен новый access token (${NEW_ACCESS_TOKEN:0:20}...)"

TMP_ENV=$(mktemp)
grep -v '^ANTHROPIC_API_KEY=' "$ENV_FILE" | grep -v '^ANTHROPIC_REFRESH_TOKEN=' | grep -v '^ANTHROPIC_TOKEN_EXPIRES_AT=' > "$TMP_ENV"
echo "ANTHROPIC_API_KEY=${NEW_ACCESS_TOKEN}" >> "$TMP_ENV"
echo "ANTHROPIC_REFRESH_TOKEN=${NEW_REFRESH_TOKEN:-$REFRESH_TOKEN}" >> "$TMP_ENV"
echo "ANTHROPIC_TOKEN_EXPIRES_AT=${EXPIRES_AT}" >> "$TMP_ENV"
mv "$TMP_ENV" "$ENV_FILE"

log "Обновлён .env. Перезапускаем quota-proxy..."
cd /opt/cortex-forge && docker compose restart quota-proxy >> "$LOG_FILE" 2>&1
log "Готово."
