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
    [ -d "$WS" ] || continue

    # SOUL.md: источником истины служит workspace/SOUL.md, Hermes читает hermes_data/SOUL.md
    if [ -f "$WS/SOUL.md" ] && [ -d "$HD" ]; then
        if [ ! -f "$HD/SOUL.md" ] || ! diff -q "$WS/SOUL.md" "$HD/SOUL.md" > /dev/null 2>&1; then
            cp "$WS/SOUL.md" "$HD/SOUL.md"
            CHANGES+=("[$NAME] SOUL.md синхронизирован в hermes_data/")
        fi
    fi

    [ "$NAME" = "$ADMIN_INSTANCE" ] && continue  # у Admin свой HEARTBEAT

    HB="$WS/HEARTBEAT.md"
    if [ ! -f "$HB" ]; then
        cp "$HEARTBEAT_REF" "$HB"
        CHANGES+=("[$NAME] HEARTBEAT.md отсутствовал — восстановлен")
    elif ! diff -q "$HB" "$HEARTBEAT_REF" > /dev/null 2>&1; then
        cp "$HEARTBEAT_REF" "$HB"
        CHANGES+=("[$NAME] HEARTBEAT.md устарел — обновлён")
    fi
done

# ─── 3. Контейнеры живы? ───────────────────────────────────────────────────
for INST_DIR in "$INSTANCES"/*/; do
    NAME=$(basename "$INST_DIR")
    [ "$NAME" = "_template" ] && continue
    [ "$NAME" = "$ADMIN_INSTANCE" ] && continue  # admin manages itself

    CONTAINER="corp-$NAME"
    STATUS=$(docker inspect --format '{{.State.Status}}' "$CONTAINER" 2>/dev/null || echo "not_found")

    if [ "$STATUS" != "running" ]; then
        # Пробуем поднять (cd в /infra/ чтобы compose нашёл и base, и override)
        (cd "$INFRA" && docker compose up -d "assistant-$NAME" 2>&1) || true
        CHANGES+=("[$NAME] контейнер был '$STATUS' — попытка запуска")
    fi
done

# ─── Итог ──────────────────────────────────────────────────────────────────
if [ ${#CHANGES[@]} -eq 0 ]; then
    echo "ALL_OK"
else
    printf '%s\n' "${CHANGES[@]}"
fi
