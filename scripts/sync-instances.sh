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

# ─── 2. Эталонный HEARTBEAT (берём из никиты как эталон) ───────────────────
HEARTBEAT_REF="$INSTANCES/user-1/openclaw_data/workspace/HEARTBEAT.md"

for INST_DIR in "$INSTANCES"/*/; do
    NAME=$(basename "$INST_DIR")
    [ "$NAME" = "_template" ] && continue
    [ "$NAME" = "$ADMIN_INSTANCE" ] && continue  # у Adminа свой HEARTBEAT

    WS="$INST_DIR/openclaw_data/workspace"
    [ -d "$WS" ] || continue

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

    CONTAINER="corp-$NAME"
    STATUS=$(docker inspect --format '{{.State.Status}}' "$CONTAINER" 2>/dev/null || echo "not_found")

    if [ "$STATUS" != "running" ]; then
        # Пробуем поднять
        docker compose -f "$INFRA/docker-compose.yml" up -d "$CONTAINER" 2>&1 || true
        CHANGES+=("[$NAME] контейнер был '$STATUS' — попытка запуска")
    fi
done

# ─── Итог ──────────────────────────────────────────────────────────────────
if [ ${#CHANGES[@]} -eq 0 ]; then
    echo "ALL_OK"
else
    printf '%s\n' "${CHANGES[@]}"
fi
