#!/usr/bin/env bash
# remove-user.sh — удаление инстанса сотрудника
set -e

NAME="$1"

# Валидация имени: только a-z0-9-_ (защита от path traversal)
if ! echo "$NAME" | grep -qE '^[a-z][a-z0-9_-]{1,31}$'; then
  echo "❌ Недопустимое имя '$NAME'. Только a-z, 0-9, -, _ (2-32 символа, начинается с буквы)"
  exit 1
fi

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

# Удаляем ключи из глобального .env
NAME_UPPER=$(echo "$NAME" | tr '[:lower:]' '[:upper:]')
if [ -f ".env" ]; then
    # Удаляем строки BROKER_KEY_*, QUOTA_KEY_*, QUOTA_LIMIT_* для этого пользователя
    python3 -c "
import sys, re
name_upper = sys.argv[1]
patterns = [f'BROKER_KEY_{name_upper}=', f'QUOTA_KEY_{name_upper}=', f'QUOTA_LIMIT_{name_upper}=']
with open('.env') as f:
    lines = f.readlines()
kept = [l for l in lines if not any(l.startswith(p) for p in patterns)]
with open('.env', 'w') as f:
    f.writelines(kept)
removed = len(lines) - len(kept)
print(f'  ✅ Удалено {removed} ключей из .env')
" "$NAME_UPPER"
fi

# Удаляем сервис из docker-compose.override.yml (построчный парсинг — безопаснее regex)
python3 -c "
import sys
name = sys.argv[1]
service_key = f'  assistant-{name}:'

with open('docker-compose.override.yml') as f:
    lines = f.readlines()

result = []
in_block = False
found = False

for line in lines:
    stripped = line.rstrip()

    # Обнаруживаем начало целевого блока сервиса (ровно 2 пробела отступа)
    if stripped == service_key:
        in_block = True
        found = True
        continue

    if in_block:
        # Конец блока: строка с отступом <= 2 пробел и непустая (следующий сервис
        # или топ-уровневый ключ типа 'volumes:' / 'networks:')
        if line and not line.startswith('   ') and stripped:
            in_block = False
            result.append(line)
        # Иначе — пропускаем строки текущего блока
        continue

    result.append(line)

if found:
    with open('docker-compose.override.yml', 'w') as f:
        f.writelines(result)
    print(f'  ✅ assistant-{name} удалён из docker-compose.override.yml')
else:
    print(f'  ⚠️  assistant-{name} не найден в docker-compose.override.yml')
" "$NAME"

echo ""
echo "✅ Удаление '$NAME' завершено полностью"
