#!/usr/bin/env bash
# Полное автообновление CortexForge — запускается кроном каждые 5 минут.
#
# Логика:
#   1. git pull  → post-merge hook делает миграции + рестарт изменившихся контейнеров
#   2. docker pull (только внешние образы) + docker compose build (локальные)
#      → up -d если что-то поменялось

set -uo pipefail  # без -e — обрабатываем ошибки вручную

REPO=/opt/cortex-forge
LOG=$REPO/logs/autoupdate.log
LOCK=$REPO/logs/autoupdate.lock

mkdir -p "$REPO/logs"

# Лок — не запускаем параллельно
exec 9>"$LOCK"
if ! flock -n 9; then
  exit 0
fi

cd "$REPO"

log() { echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') $*" | tee -a "$LOG"; }

CHANGED=false

# ── 1. Git ────────────────────────────────────────────────────────────────────
git fetch origin master -q 2>/dev/null || true

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/master)

if [ "$LOCAL" != "$REMOTE" ]; then
  log "📦 Код: $(git log --oneline "${LOCAL}".."${REMOTE}" | head -3)"
  git pull origin master 2>&1 | tee -a "$LOG"
  git submodule update --remote --recursive -q 2>&1 | tee -a "$LOG"
  CHANGED=true
fi

# ── 2. Внешние Docker образы (openclaw:latest и др.) ─────────────────────────
PULLED=$(docker compose pull --ignore-buildable 2>&1 || true)
if echo "$PULLED" | grep -q "Pulled"; then
  log "🐳 Новые внешние образы:"
  echo "$PULLED" | grep "Pulled" | tee -a "$LOG"
  CHANGED=true
fi

# ── 3. Локальные образы — пересобираем если Dockerfile изменился ─────────────
REBUILD=false
if [ "$LOCAL" != "$REMOTE" ]; then
  if git diff --name-only "${LOCAL}" HEAD 2>/dev/null | grep -qE "Dockerfile|docker-compose"; then
    REBUILD=true
  fi
fi

if [ "$REBUILD" = "true" ]; then
  log "🔨 Пересобираем локальные образы..."
  docker compose build 2>&1 | tee -a "$LOG"
  CHANGED=true
fi

# ── 4. Если что-то изменилось — поднимаем все сервисы ────────────────────────
if [ "$CHANGED" = "true" ]; then
  log "🚀 Обновляем контейнеры..."
  docker compose up -d --remove-orphans 2>&1 | tee -a "$LOG"
  log "✅ Готово"
fi
