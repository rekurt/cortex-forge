#!/usr/bin/env bash
# add-user.sh — онбординг нового сотрудника
# Использование: bash scripts/add-user.sh <name> <bot_token> <full_name> <tg_id>

set -e

NAME="$1"
BOT_TOKEN="$2"
FULL_NAME="${3:-$NAME}"
TG_ID="${4:-}"
TEMPLATE="instances/_template"
TARGET="instances/$NAME"

if [ -d "$TARGET" ]; then
  echo "❌ Инстанс '$NAME' уже существует: $TARGET"
  exit 1
fi

echo "🚀 Создаём инстанс для: $FULL_NAME ($NAME)"

# Создаём директории
mkdir -p "$TARGET/workspace/memory"
mkdir -p "$TARGET/workspace/skills"

# Копируем шаблоны workspace
cp -r "$TEMPLATE/workspace/"* "$TARGET/workspace/"

# Подставляем имя пользователя в шаблоны
sed -i "s/{{FULL_NAME}}/$FULL_NAME/g" "$TARGET/workspace/USER.md"
sed -i "s/{{NAME}}/$NAME/g"          "$TARGET/workspace/USER.md"
sed -i "s/{{FULL_NAME}}/$FULL_NAME/g" "$TARGET/workspace/IDENTITY.md"
sed -i "s/{{NAME}}/$NAME/g"          "$TARGET/workspace/IDENTITY.md"

# Создаём .env для инстанса
cat > "$TARGET/.env" << EOF
# Секреты инстанса $NAME — НЕ коммитить в git!
TELEGRAM_BOT_TOKEN=$BOT_TOKEN
TELEGRAM_ALLOW_FROM=${TG_ID}
# Добавить персональные токены ниже:
# YANDEX_OAUTH_TOKEN=
# YANDEX_CALDAV_URL=
# YANDEX_USER=
# YANDEX_APP_PASSWORD=
# GITLAB_TOKEN=
EOF

# Копируем openclaw.json.template
cp "$TEMPLATE/openclaw.json.template" "$TARGET/openclaw.json"
sed -i "s/{{BOT_TOKEN}}/$BOT_TOKEN/g" "$TARGET/openclaw.json"
sed -i "s/{{TG_ID}}/$TG_ID/g"        "$TARGET/openclaw.json"

# Добавляем сервис в docker-compose.yml
python3 - "$NAME" << 'PYEOF'
import sys, re

name = sys.argv[1]
service = f"""
  assistant-{name}:
    image: ghcr.io/openclaw/openclaw:latest
    container_name: corp-{name}
    restart: unless-stopped
    env_file:
      - instances/{name}/.env
    volumes:
      - ./instances/{name}/workspace:/home/user/.openclaw/workspace
      - ./instances/{name}/openclaw.json:/home/user/.openclaw/openclaw.json:ro
      - ./shared/skills:/shared/skills:ro
    environment:
      - ANTHROPIC_API_KEY=${{ANTHROPIC_API_KEY}}
    labels:
      corp.assistant.user: {name}
"""

content = open("docker-compose.yml").read()
# Убираем финальный комментарий-заглушку если пусто
content = content.rstrip() + "\n" + service
open("docker-compose.yml", "w").write(content)
print(f"  ✅ Сервис assistant-{name} добавлен в docker-compose.yml")
PYEOF

echo ""
echo "✅ Инстанс '$NAME' создан: $TARGET"
echo ""
echo "📋 Следующие шаги:"
echo "  1. Заполни секреты: $TARGET/.env"
echo "  2. Настрой персонажа: $TARGET/workspace/SOUL.md"
echo "  3. make deploy"
echo "  4. Скажи $FULL_NAME написать боту первое сообщение"
