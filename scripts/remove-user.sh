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

# Удаляем сервис из docker-compose.yml
python3 -c "
import sys, re
name = sys.argv[1]
with open('docker-compose.yml') as f:
    content = f.read()

# Удаляем блок assistant-{name}: ... до следующего сервиса или секции верхнего уровня
pattern = rf'\n  assistant-{re.escape(name)}:.*?(?=\n  \S|\nvolumes:|\nnetworks:|\Z)'
new_content = re.sub(pattern, '', content, flags=re.DOTALL)

if new_content != content:
    with open('docker-compose.yml', 'w') as f:
        f.write(new_content)
    print(f'  ✅ assistant-{name} удалён из docker-compose.yml')
else:
    print(f'  ⚠️  assistant-{name} не найден в docker-compose.yml')
" "$NAME"

echo ""
echo "✅ Удаление '$NAME' завершено полностью"
