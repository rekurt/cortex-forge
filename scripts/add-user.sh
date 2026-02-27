#!/usr/bin/env bash
# add-user.sh — онбординг нового сотрудника
# Использование: make add-user NAME=user-2 BOT_TOKEN=7xxx FULL_NAME="Example User" TG_ID=123456789

set -e

NAME="$1"
BOT_TOKEN="$2"
FULL_NAME="${3:-$NAME}"
TG_ID="${4:-}"
TEMPLATE="instances/_template"
TARGET="instances/$NAME"

[ -d "$TARGET" ] && echo "❌ Инстанс '$NAME' уже существует" && exit 1

# Валидация имени: только a-z0-9-_ (защита от shell injection и path traversal)
if ! echo "$NAME" | grep -qE '^[a-z][a-z0-9_-]{1,31}$'; then
  echo "❌ Недопустимое имя '$NAME'. Только a-z, 0-9, -, _ (2-32 символа, начинается с буквы)"
  exit 1
fi

echo "🚀 Создаём инстанс: $FULL_NAME ($NAME)"

mkdir -p "$TARGET/workspace/memory"

# Копируем шаблоны воркспейса
cp -r "$TEMPLATE/workspace/"* "$TARGET/workspace/"
# Используем Python для подстановки — безопасно для спецсимволов в FULL_NAME (/, &, \)
python3 -c "
import sys, pathlib
name, full_name = sys.argv[1], sys.argv[2]
for fname in ['USER.md', 'IDENTITY.md']:
    p = pathlib.Path(f'$TARGET/workspace/{fname}')
    if p.exists():
        text = p.read_text()
        text = text.replace('{{FULL_NAME}}', full_name).replace('{{NAME}}', name)
        p.write_text(text)
" "$NAME" "$FULL_NAME"

# Генерируем ключи
BROKER_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
QUOTA_KEY=$(python3 -c "import secrets; print('quota-${NAME}-' + secrets.token_urlsafe(24))")
NAME_UPPER=$(echo "$NAME" | tr '[:lower:]' '[:upper:]')

# .env инстанса
cat > "$TARGET/.env" << EOF
# Секреты инстанса $NAME — НЕ коммитить в git!
TELEGRAM_BOT_TOKEN=$BOT_TOKEN
TELEGRAM_ALLOW_FROM=${TG_ID}

# Broker & Quota
BROKER_URL=http://message-broker:8080
BROKER_KEY=$BROKER_KEY

# Персональные токены:
# YANDEX_OAUTH_TOKEN=
# YANDEX_CALDAV_URL=
# YANDEX_USER=
# YANDEX_APP_PASSWORD=
# GITLAB_TOKEN=
EOF

# OpenClaw конфиг
cp "$TEMPLATE/openclaw.json.template" "$TARGET/openclaw.json"
sed -i "s/{{BOT_TOKEN}}/$BOT_TOKEN/g" "$TARGET/openclaw.json"
sed -i "s/{{TG_ID}}/$TG_ID/g"        "$TARGET/openclaw.json"

# Добавляем ключи в глобальный .env
if [ -f ".env" ]; then
    echo "BROKER_KEY_${NAME_UPPER}=${BROKER_KEY}"  >> .env
    echo "QUOTA_KEY_${NAME_UPPER}=${QUOTA_KEY}"    >> .env
    echo "QUOTA_LIMIT_${NAME_UPPER}=1000000"       >> .env  # 1M токенов/мес по умолчанию
    echo "  ✅ Ключи добавлены в .env"
fi

# Добавляем сервис в docker-compose.yml
python3 - "$NAME" "$NAME_UPPER" << 'PYEOF'
import sys
name, NAME_UPPER = sys.argv[1], sys.argv[2]

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
      - ANTHROPIC_API_KEY=${{{f"QUOTA_KEY_{NAME_UPPER}"}}}
      - ANTHROPIC_BASE_URL=http://quota-proxy:9090
      - BROKER_URL=http://message-broker:8080
      - BROKER_KEY=${{{f"BROKER_KEY_{NAME_UPPER}"}}}
    networks:
      - corp-internal
    security_opt:
      - no-new-privileges:true
    deploy:
      resources:
        limits:
          cpus: "1.0"
          memory: 512M
    depends_on:
      quota-proxy:
        condition: service_healthy
      message-broker:
        condition: service_healthy
    labels:
      corp.assistant.role: personal
      corp.assistant.user: {name}
"""

content = open("docker-compose.yml").read()
content = content.replace("\nvolumes:", service + "\nvolumes:")
open("docker-compose.yml", "w").write(content)
print(f"  ✅ assistant-{name} добавлен в docker-compose.yml")
PYEOF

echo ""
echo "✅ Инстанс '$NAME' создан"
echo "   Квота: 1,000,000 токенов/мес (изменить: make set-limit NAME=$NAME LIMIT=500000)"
echo ""
echo "📋 Далее:"
echo "  1. nano instances/$NAME/.env          — персональные токены"
echo "  2. nano instances/$NAME/workspace/SOUL.md  — настроить персонажа"
echo "  3. make deploy"
