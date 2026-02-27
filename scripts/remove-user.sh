#!/usr/bin/env bash
# remove-user.sh — удаление инстанса сотрудника
set -e

NAME="$1"
TARGET="instances/$NAME"

[ -d "$TARGET" ] || (echo "❌ Инстанс '$NAME' не найден"; exit 1)

echo "⚠️  Удаляем инстанс: $NAME"
read -p "Уверен? (yes/no): " CONFIRM
[ "$CONFIRM" = "yes" ] || (echo "Отмена."; exit 0)

# Останавливаем контейнер
docker compose stop "assistant-$NAME" 2>/dev/null || true
docker compose rm -f "assistant-$NAME" 2>/dev/null || true

# Архивируем воркспейс перед удалением
ARCHIVE="backups/${NAME}-$(date +%Y%m%d).tar.gz"
mkdir -p backups
tar -czf "$ARCHIVE" "$TARGET/workspace" 2>/dev/null || true
echo "📦 Архив сохранён: $ARCHIVE"

# Удаляем директорию
rm -rf "$TARGET"
echo "✅ Инстанс '$NAME' удалён"
echo "💡 Не забудь убрать сервис assistant-$NAME из docker-compose.yml"
