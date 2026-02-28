#!/usr/bin/env bash
# Автообновление CortexForge — запускается кроном каждые 5 минут.
# git pull → post-merge hook → миграции → рестарт изменившихся контейнеров.
set -e

REPO=/opt/cortex-forge
LOG=/opt/cortex-forge/logs/autoupdate.log

mkdir -p "$(dirname "$LOG")"

cd "$REPO"

# Проверяем есть ли обновления
git fetch origin master --quiet 2>&1

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/master)

if [ "$LOCAL" = "$REMOTE" ]; then
  # Нет обновлений — тихо выходим
  exit 0
fi

echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') [autoupdate] Обновление: $LOCAL → $REMOTE" | tee -a "$LOG"

# git pull запускает post-merge hook автоматически
git pull origin master 2>&1 | tee -a "$LOG"

echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') [autoupdate] Готово" | tee -a "$LOG"
