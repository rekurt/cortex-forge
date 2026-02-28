#!/bin/bash
# backup.sh — Резервное копирование данных инстансов
# 1. git commit изменений в /infra
# 2. tar.gz архив instances/ → /infra/backups/
#
# ВАЖНО: git push выполняется только с хост-машины (root@89.167.99.119).
# Из контейнера делаем только commit; push запускается отдельно на хосте.

set -euo pipefail

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
    git commit -m "chore: hourly backup $TIMESTAMP [Приор]" 2>&1
    CHANGES+=("git: commit $TIMESTAMP")
fi

# ─── 2. Архив instances/ ─────────────────────────────────────────────────────
tar -czf "$ARCHIVE" \
    --exclude="instances/*/openclaw_data/agents/main/sessions/*.jsonl" \
    instances/ 2>&1

SIZE=$(du -sh "$ARCHIVE" | cut -f1)
CHANGES+=("архив: $ARCHIVE ($SIZE)")

# ─── 3. Ротация — оставляем только последние 48 архивов (~2 суток) ───────────
ls -t "$BACKUPS"/instances_*.tar.gz 2>/dev/null | tail -n +49 | xargs -r rm -f
KEPT=$(ls "$BACKUPS"/instances_*.tar.gz 2>/dev/null | wc -l)
CHANGES+=("ротация: сохранено $KEPT архивов")

# ─── Итог ────────────────────────────────────────────────────────────────────
printf '%s\n' "${CHANGES[@]}"
