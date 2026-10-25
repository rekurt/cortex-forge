#!/bin/bash
# backup.sh — Резервное копирование данных инстансов
# 1. git commit изменений в /infra
# 2. tar.gz архив instances/ → /infra/backups/
#
# ВАЖНО: git push выполняется только с хост-машины (root@89.167.99.119).
# Из контейнера делаем только commit; push запускается отдельно на хосте.

set -euo pipefail
umask 077

INFRA="/infra"
BACKUPS="$INFRA/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
ARCHIVE="$BACKUPS/instances_$TIMESTAMP.tar.gz"
CHANGES=()

mkdir -p "$BACKUPS"

# ─── 1. Git commit ───────────────────────────────────────────────────────────
cd "$INFRA"

if git diff --quiet && git diff --cached --quiet; then
    CHANGES+=("git: нет изменений")
else
    git add -A
    git commit -m "chore: hourly backup $TIMESTAMP [Admin]" 2>&1
    CHANGES+=("git: commit $TIMESTAMP")
fi

# ─── 2. Архив instances/ (без сессий, .env-секретов и приватных SSH-ключей) ──
tar -czf "$ARCHIVE" \
    --exclude="instances/*/hermes_data/sessions/*" \
    --exclude="instances/*/hermes_data/ssh/*" \
    --exclude="instances/*/.env" \
    --exclude="instances/*/hermes_data/.env" \
    instances/ 2>&1
chmod 600 "$ARCHIVE"

SIZE=$(du -sh "$ARCHIVE" | cut -f1)
CHANGES+=("архив: $ARCHIVE ($SIZE)")

# ─── 3. Ротация — оставляем только последние 48 архивов (~2 суток) ───────────
find "$BACKUPS" -maxdepth 1 -name 'instances_*.tar.gz' -type f -print0 2>/dev/null \
  | xargs -0 ls -t 2>/dev/null | tail -n +49 | xargs -r rm -f
KEPT=$(find "$BACKUPS" -maxdepth 1 -name 'instances_*.tar.gz' -type f 2>/dev/null | wc -l | tr -d ' ')
CHANGES+=("ротация: сохранено $KEPT архивов")

# ─── Итог ────────────────────────────────────────────────────────────────────
printf '%s\n' "${CHANGES[@]}"
