#!/usr/bin/env bash
# add-user.sh — онбординг нового сотрудника
# Использование: make add-user NAME=user-2 BOT_TOKEN=7xxx FULL_NAME="Example User" TG_ID=123456789

set -e

NAME="$1"
BOT_TOKEN="$2"
FULL_NAME="${3:-$NAME}"
TG_ID="${4:-}"
UI_PORT="${5:-}"

# Авто-порт: считаем существующие инстансы и берём 18790+N
if [ -z "$UI_PORT" ]; then
  INSTANCE_COUNT=$(find instances -mindepth 1 -maxdepth 1 -type d ! -name "_template" ! -name "admin" | wc -l | tr -d ' ')
  UI_PORT=$((18790 + INSTANCE_COUNT))
fi
TEMPLATE="instances/_template"
TARGET="instances/$NAME"

[ -d "$TARGET" ] && echo "❌ Инстанс '$NAME' уже существует" && exit 1

# Валидация имени: только a-z0-9-_ (защита от shell injection и path traversal)
if ! echo "$NAME" | grep -qE '^[a-z][a-z0-9_-]{1,31}$'; then
  echo "❌ Недопустимое имя '$NAME'. Только a-z, 0-9, -, _ (2-32 символа, начинается с буквы)"
  exit 1
fi

echo "🚀 Создаём инстанс: $FULL_NAME ($NAME)"

mkdir -p "$TARGET/openclaw_data/workspace/memory"

# Копируем шаблоны воркспейса
cp -r "$TEMPLATE/workspace/"* "$TARGET/openclaw_data/workspace/"
# Используем Python для подстановки — безопасно для спецсимволов в FULL_NAME (/, &, \)
python3 -c "
import sys, pathlib
name, full_name = sys.argv[1], sys.argv[2]
for fname in ['USER.md', 'IDENTITY.md']:
    p = pathlib.Path(f'$TARGET/openclaw_data/workspace/{fname}')
    if p.exists():
        text = p.read_text()
        text = text.replace('{{FULL_NAME}}', full_name).replace('{{NAME}}', name)
        p.write_text(text)
" "$NAME" "$FULL_NAME"

# Генерируем ключи
BROKER_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
QUOTA_KEY=$(python3 -c "import secrets; print('quota-${NAME}-' + secrets.token_urlsafe(24))")
GATEWAY_TOKEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
NAME_UPPER=$(echo "$NAME" | tr '[:lower:]' '[:upper:]')

# .env инстанса
cat > "$TARGET/.env" << EOF
# Секреты инстанса $NAME — НЕ коммитить в git!
TELEGRAM_BOT_TOKEN=$BOT_TOKEN
TELEGRAM_ALLOW_FROM=${TG_ID}
GATEWAY_TOKEN=$GATEWAY_TOKEN

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

# OpenClaw конфиг — кладём внутрь openclaw_data/ (единственный mount)
cp "$TEMPLATE/openclaw.json.template" "$TARGET/openclaw_data/openclaw.json"
python3 -c "
import sys, pathlib
bot_token, tg_id, path = sys.argv[1], sys.argv[2], sys.argv[3]
p = pathlib.Path(path)
text = p.read_text()
text = text.replace('{{BOT_TOKEN}}', bot_token).replace('{{TG_ID}}', tg_id)
p.write_text(text)
" "$BOT_TOKEN" "$TG_ID" "$TARGET/openclaw_data/openclaw.json"

# Выставляем владельца — OpenClaw работает от uid 1000 (node)
chown -R 1000:1000 "$TARGET/openclaw_data" 2>/dev/null || true

# Добавляем ключи в глобальный .env
if [ -f ".env" ]; then
    echo "BROKER_KEY_${NAME_UPPER}=${BROKER_KEY}"  >> .env
    echo "QUOTA_KEY_${NAME_UPPER}=${QUOTA_KEY}"    >> .env
    echo "QUOTA_LIMIT_${NAME_UPPER}=1000000"       >> .env  # 1M токенов/мес по умолчанию
    echo "  ✅ Ключи добавлены в .env"
fi

# Добавляем сервис в docker-compose.override.yml (gitignored — не конфликтует с git pull)
python3 - "$NAME" "$NAME_UPPER" "$UI_PORT" << 'PYEOF'
import sys, pathlib
name, NAME_UPPER, ui_port = sys.argv[1], sys.argv[2], sys.argv[3]
OVERRIDE = "docker-compose.override.yml"

service = f"""
  assistant-{name}:
    build:
      context: .
      dockerfile: instances/Dockerfile.user
    image: cortex-forge-user:latest
    container_name: corp-{name}
    restart: unless-stopped
    env_file:
      - instances/{name}/.env
    volumes:
      - ./instances/{name}/openclaw_data:/home/node/.openclaw
      - ./shared/skills:/shared/skills:ro
    environment:
      - ANTHROPIC_API_KEY=${{ANTHROPIC_API_KEY}}
      - OPENAI_API_KEY=${{OPENAI_API_KEY}}
      - BROKER_URL=http://message-broker:8080
      - BROKER_KEY=${{{f"BROKER_KEY_{NAME_UPPER}"}}}
      - NODE_OPTIONS=--max-old-space-size=1024
    ports:
      - "127.0.0.1:{ui_port}:18789"   # OpenClaw Control UI
    networks:
      - corp-internal    # quota-proxy + broker (internal)
      - corp-outbound    # Telegram API + внешние вызовы
    security_opt:
      - no-new-privileges:true
    deploy:
      resources:
        limits:
          cpus: "2.0"
          memory: 1G
    depends_on:
      quota-proxy:
        condition: service_healthy
      message-broker:
        condition: service_healthy
    labels:
      corp.assistant.role: personal
      corp.assistant.user: {name}
"""

p = pathlib.Path(OVERRIDE)
if p.exists():
    content = p.read_text()
    # append before end or after last service
    content = content.rstrip() + "\n" + service
else:
    content = "services:" + service

p.write_text(content)
print(f"  ✅ assistant-{name} добавлен в {OVERRIDE}")
PYEOF

echo ""
echo "✅ Инстанс '$NAME' создан"
echo "   Квота: 1,000,000 токенов/мес (изменить: make set-limit NAME=$NAME LIMIT=500000)"
echo "   Control UI: http://localhost:$UI_PORT"
echo ""
echo "📋 Далее:"
echo "  1. nano instances/$NAME/.env               — персональные токены"
echo "  2. nano instances/$NAME/workspace/SOUL.md  — настроить персонажа"
echo "  3. make deploy"
