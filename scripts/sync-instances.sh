#!/bin/bash
# sync-instances.sh — Актуализатор обезьян
# Admin запускает каждый час: проверяет и синхронизирует все инстансы.
# Возвращает список изменений или "ALL_OK" если всё актуально.

set -euo pipefail

INFRA="/infra"
INSTANCES="$INFRA/instances"
ADMIN_INSTANCE="admin"
CHANGES=()

# ─── 1. Миграции ────────────────────────────────────────────────────────────
MIGRATE_OUT=$(cd "$INFRA" && python3 scripts/migrate-instances.py 2>&1)
if echo "$MIGRATE_OUT" | grep -qv "актуален"; then
    CHANGES+=("Миграции: $MIGRATE_OUT")
fi

# ─── 2. Эталонный HEARTBEAT и синхронизация SOUL.md → hermes_data/ ──────────
HEARTBEAT_REF="$INSTANCES/_template/workspace/HEARTBEAT.md"

for INST_DIR in "$INSTANCES"/*/; do
    NAME=$(basename "$INST_DIR")
    [ "$NAME" = "_template" ] && continue

    WS="$INSTANCES/$NAME/workspace"
    HD="$INSTANCES/$NAME/hermes_data"
    [ -d "$WS" ] && [ ! -L "$WS" ] || continue

    # SOUL.md: источником истины служит workspace/SOUL.md, Hermes читает hermes_data/SOUL.md (отклоняем симлинки)
    if [ -f "$WS/SOUL.md" ] && [ ! -L "$WS/SOUL.md" ] && [ -d "$HD" ] && [ ! -L "$HD" ] && [ ! -L "$HD/SOUL.md" ]; then
        if [ ! -f "$HD/SOUL.md" ] || ! diff -q "$WS/SOUL.md" "$HD/SOUL.md" > /dev/null 2>&1; then
            cp -P "$WS/SOUL.md" "$HD/SOUL.md"
            CHANGES+=("[$NAME] SOUL.md синхронизирован в hermes_data/")
        fi
    fi

    [ "$NAME" = "$ADMIN_INSTANCE" ] && continue  # у Admin свой HEARTBEAT

    HB="$WS/HEARTBEAT.md"
    if [ -L "$HB" ]; then
        rm -f "$HB"
        cp "$HEARTBEAT_REF" "$HB"
        CHANGES+=("[$NAME] HEARTBEAT.md был симлинком — пересоздан из эталона")
    elif [ ! -f "$HB" ]; then
        cp "$HEARTBEAT_REF" "$HB"
        CHANGES+=("[$NAME] HEARTBEAT.md отсутствовал — восстановлен")
    elif ! diff -q "$HB" "$HEARTBEAT_REF" > /dev/null 2>&1; then
        cp "$HEARTBEAT_REF" "$HB"
        CHANGES+=("[$NAME] HEARTBEAT.md устарел — обновлён")
    fi
done

# ─── 3. Контейнеры живы? (O(1) docker ps -a для 1000 инстансов) ────────────
RUNNING_MAP=$(docker ps -a --format '{{.Names}}={{.State}}' 2>/dev/null || true)
STOPPED_SERVICES=()

for INST_DIR in "$INSTANCES"/*/; do
    NAME=$(basename "$INST_DIR")
    [ "$NAME" = "_template" ] && continue
    [ "$NAME" = "$ADMIN_INSTANCE" ] && continue  # admin manages itself

    CONTAINER="corp-$NAME"
    STATUS=$(echo "$RUNNING_MAP" | grep -E "^${CONTAINER}=" | head -1 | cut -d= -f2- || true)
    [ -z "$STATUS" ] && STATUS="not_found"

    if [ "$STATUS" != "running" ]; then
        STOPPED_SERVICES+=("assistant-$NAME")
        CHANGES+=("[$NAME] контейнер был '$STATUS' — добавлен в очередь запуска")
    fi
done

if [ ${#STOPPED_SERVICES[@]} -gt 0 ]; then
    # Запускаем упавшие сервисы батчами по 50, чтобы не перегрузить демон при 1000 инстансах
    (
        cd "$INFRA"
        printf '%s\n' "${STOPPED_SERVICES[@]}" | xargs -n 50 docker compose up -d 2>&1
    ) || true
fi

# ─── Итог ──────────────────────────────────────────────────────────────────
if [ ${#CHANGES[@]} -eq 0 ]; then
    echo "ALL_OK"
else
    printf '%s\n' "${CHANGES[@]}"
fi
