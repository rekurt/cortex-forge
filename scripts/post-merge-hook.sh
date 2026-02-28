#!/usr/bin/env bash
# Git post-merge hook — автоперезапуск при git pull
# Устанавливается через: make install-hooks
set -e

COMPOSE="docker compose"
REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

echo "🔄 [post-merge] Проверяю изменения..."

# Список файлов изменившихся в последнем merge
CHANGED=$(git diff-tree -r --name-only --no-commit-id ORIG_HEAD HEAD 2>/dev/null || true)

if [ -z "$CHANGED" ]; then
  echo "  Нет изменений — пропускаю."
  exit 0
fi

# Обновить субмодули (compliance-risk и др.)
if echo "$CHANGED" | grep -qE '(\.gitmodules|shared/skills/)'; then
  echo "  📦 Обновляю субмодули..."
  git submodule update --init --recursive
fi

RESTART=""
REBUILD=""

# Проверяем что изменилось
echo "$CHANGED" | while read -r f; do
  case "$f" in
    quota-proxy/*)       echo "quota-proxy" >> /tmp/.cf_rebuild ;;
    broker/*)            echo "message-broker" >> /tmp/.cf_rebuild ;;
    resource-monitor/*)  echo "resource-monitor" >> /tmp/.cf_rebuild ;;
    service-agent/*)     echo "assistant-service" >> /tmp/.cf_rebuild ;;
    instances/admin/Dockerfile) echo "assistant-admin" >> /tmp/.cf_rebuild ;;
    docker-compose.yml)  echo "__all__" >> /tmp/.cf_rebuild ;;
  esac
  case "$f" in
    shared/skills/*)     echo "user-instances" >> /tmp/.cf_restart ;;
    instances/_template/*) : ;;  # шаблон — инстансы не трогаем
  esac
done

REBUILD_LIST=""
if [ -f /tmp/.cf_rebuild ]; then
  REBUILD_LIST=$(sort -u /tmp/.cf_rebuild)
  rm -f /tmp/.cf_rebuild
fi

RESTART_LIST=""
if [ -f /tmp/.cf_restart ]; then
  RESTART_LIST=$(sort -u /tmp/.cf_restart)
  rm -f /tmp/.cf_restart
fi

# Полный рестарт если docker-compose.yml изменился
if echo "$REBUILD_LIST" | grep -q "__all__"; then
  echo "  🐳 docker-compose.yml изменился — пересобираю всё..."
  $COMPOSE up -d --build 2>&1 | grep -E "(Building|built|Started|Recreated|error)" || true
  echo "  🗄️  Применяю миграции воркспейсов..."
  MIGRATE_OUT=$(python3 "$REPO_ROOT/scripts/migrate-instances.py")
  echo "$MIGRATE_OUT" | grep -v "^MIGRATED_INSTANCES:" || true
  MIGRATED=$(echo "$MIGRATE_OUT" | grep "^MIGRATED_INSTANCES:" | sed 's/^MIGRATED_INSTANCES: //')
  if [ -n "$MIGRATED" ]; then
    echo "  🔁 Перезапускаю обновлённые инстансы: $MIGRATED"
    for name in $MIGRATED; do
      $COMPOSE restart "assistant-$name" 2>&1 | grep -E "(Restarting|Started|error)" || true
    done
  fi
  echo "  ✅ Готово."
  exit 0
fi

# Пересборка изменившихся сервисов
if [ -n "$REBUILD_LIST" ]; then
  for svc in $REBUILD_LIST; do
    echo "  🔨 Пересобираю $svc..."
    $COMPOSE up -d --build "$svc" 2>&1 | grep -E "(Building|built|Started|Recreated|error)" || true
  done
fi

# Рестарт пользовательских инстансов (обновились скиллы)
if echo "$RESTART_LIST" | grep -q "user-instances"; then
  echo "  🔁 Обновились shared/skills — перезапускаю пользовательские инстансы..."
  USERS=$($COMPOSE ps --services 2>/dev/null | grep -v -E "^(assistant-admin|quota-proxy|message-broker|resource-monitor|assistant-service)$" | grep "assistant-" || true)
  if [ -n "$USERS" ]; then
    $COMPOSE restart $USERS 2>&1 | grep -E "(Restarting|Started|error)" || true
  fi
fi

# Применить миграции воркспейсов инстансов
echo "  🗄️  Применяю миграции воркспейсов..."
MIGRATE_OUT=$(python3 "$REPO_ROOT/scripts/migrate-instances.py")
echo "$MIGRATE_OUT" | grep -v "^MIGRATED_INSTANCES:" || true

# Автоперезапуск инстансов у которых обновились файлы
MIGRATED=$(echo "$MIGRATE_OUT" | grep "^MIGRATED_INSTANCES:" | sed 's/^MIGRATED_INSTANCES: //')
if [ -n "$MIGRATED" ]; then
  echo "  🔁 Перезапускаю обновлённые инстансы: $MIGRATED"
  for name in $MIGRATED; do
    $COMPOSE restart "assistant-$name" 2>&1 | grep -E "(Restarting|Started|error)" || true
  done
fi

echo "  ✅ Готово."
