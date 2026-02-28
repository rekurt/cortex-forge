#!/usr/bin/env bash
# Полное автообновление CortexForge — запускается кроном каждые 5 минут.
#
# Логика:
#   1. git pull  → post-merge hook сам делает миграции + рестарт изменившихся контейнеров
#   2. docker pull → если образы обновились — up -d пересоздаёт контейнеры с новыми образами
#
# Двойного рестарта нет: hook трогает только контейнеры с изменившимся кодом,
# up -d трогает только контейнеры с обновившимися образами.

set -euo pipefail

REPO=/opt/cortex-forge
LOG=$REPO/logs/autoupdate.log
LOCK=$REPO/logs/autoupdate.lock

mkdir -p "$REPO/logs"

# Лок — не запускаем параллельно
exec 9>"$LOCK"
if ! flock -n 9; then
  exit 0  # уже запущен
fi

cd "$REPO"

log() { echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') $*" | tee -a "$LOG"; }

# ── 1. Git ────────────────────────────────────────────────────────────────────
git fetch origin master -q

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/master)

if [ "$LOCAL" != "$REMOTE" ]; then
  log "📦 Код: $(git log --oneline "$LOCAL".."$REMOTE" | head -3)"
  # git pull запускает post-merge hook → миграции + рестарт затронутых контейнеров
  git pull origin master 2>&1 | tee -a "$LOG"
  git submodule update --remote --recursive -q 2>&1 | tee -a "$LOG"
fi

# ── 2. Docker образы ──────────────────────────────────────────────────────────
PULLED=$(docker compose pull 2>&1)
if echo "$PULLED" | grep -q "Pulled"; then
  log "🐳 Новые образы — пересоздаём контейнеры..."
  echo "$PULLED" | grep "Pulled" | tee -a "$LOG"
  docker compose up -d --remove-orphans 2>&1 | tee -a "$LOG"
  log "✅ Контейнеры пересозданы с новыми образами"
fi

# ── 3. Если всё без изменений — тихий выход ──────────────────────────────────
if [ "$LOCAL" = "$REMOTE" ] && ! echo "$PULLED" | grep -q "Pulled"; then
  exit 0
fi

log "✅ Готово"
