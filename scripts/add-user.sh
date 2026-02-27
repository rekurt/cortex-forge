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

# Подставляем имя
sed -i "s/{{FULL_NAME}}/$FULL_NAME/g" "$TARGET/workspace/USER.md"
sed -i "s/{{NAME}}/$NAME/g"          "$TARGET/workspace/USER.md"
sed -i "s/{{FULL_NAME}}/$FULL_NAME/g" "$TARGET/workspace/IDENTITY.md"
sed -i "s/{{NAME}}/$NAME/g"          "$TARGET/workspace/IDENTITY.md"

# Генерируем уникальный API-ключ для брокера
BROKER_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")

# .env инстанса
cat > "$TARGET/.env" << EOF
# Секреты инстанса $NAME — НЕ коммитить в git!
TELEGRAM_BOT_TOKEN=$BOT_TOKEN
TELEGRAM_ALLOW_FROM=${TG_ID}

# Message broker
BROKER_URL=http://message-broker:8080
BROKER_KEY=$BROKER_KEY

# Персональные токены:
# YANDEX_OAUTH_TOKEN=
# YANDEX_CALDAV_URL=
# YANDEX_USER=
# YANDEX_APP_PASSWORD=
# GITLAB_TOKEN=
EOF

# Добавляем ключ брокера в глобальный .env
NAME_UPPER=$(echo "$NAME" | tr '[:lower:]' '[:upper:]')
if [ -f ".env" ]; then
  echo "BROKER_KEY_${NAME_UPPER}=${BROKER_KEY}" >> .env
  echo "  ✅ BROKER_KEY_${NAME_UPPER} добавлен в .env"
fi

# openclaw.json
cp "$TEMPLATE/openclaw.json.template" "$TARGET/openclaw.json"
sed -i "s/{{BOT_TOKEN}}/$BOT_TOKEN/g" "$TARGET/openclaw.json"
sed -i "s/{{TG_ID}}/$TG_ID/g"        "$TARGET/openclaw.json"

# Добавляем сервис в docker-compose.yml
python3 - "$NAME" << 'PYEOF'
import sys, re

name = sys.argv[1]
NAME_UPPER = name.upper()

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
      - BROKER_URL=http://message-broker:8080
      - BROKER_KEY=${{{f"BROKER_KEY_{NAME_UPPER}"}}}
    networks:
      - corp-net
    depends_on:
      - message-broker
    labels:
      corp.assistant.role: personal
      corp.assistant.user: {name}
"""

content = open("docker-compose.yml").read()
# Вставляем перед блоком networks:
content = content.replace("\nnetworks:", service + "\nnetworks:")
open("docker-compose.yml", "w").write(content)
print(f"  ✅ Сервис assistant-{name} добавлен в docker-compose.yml")
PYEOF

echo ""
echo "✅ Инстанс '$NAME' создан: $TARGET"
echo ""
echo "📋 Следующие шаги:"
echo "  1. Заполни секреты: nano $TARGET/.env"
echo "  2. Настрой персонажа: nano $TARGET/workspace/SOUL.md"
echo "  3. make deploy"
