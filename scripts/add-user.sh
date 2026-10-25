#!/usr/bin/env bash
# add-user.sh — онбординг нового сотрудника
# Использование: make add-user NAME=user-2 BOT_TOKEN=7xxx FULL_NAME="Example User" TG_ID=123456789

set -e

NAME="$1"
BOT_TOKEN="$2"
FULL_NAME="${3:-$NAME}"
TG_ID="${4:-}"
UI_PORT="${5:-}"

# Валидация имени: только a-z0-9-_ (защита от shell injection и path traversal)
if ! echo "$NAME" | grep -qE '^[a-z][a-z0-9_-]{1,31}$'; then
  echo "❌ Недопустимое имя '$NAME'. Только a-z, 0-9, -, _ (2-32 символа, начинается с буквы)"
  exit 1
fi

# Валидация BOT_TOKEN: стандартный формат Telegram bot token (digits:alnum)
if [ -n "$BOT_TOKEN" ] && ! echo "$BOT_TOKEN" | grep -qE '^[0-9]+:[A-Za-z0-9_-]+$'; then
  echo "❌ Недопустимый формат BOT_TOKEN. Ожидается: digits:alphanumeric"
  exit 1
fi

# Валидация TG_ID: только цифры (Telegram user ID)
if [ -n "$TG_ID" ] && ! echo "$TG_ID" | grep -qE '^[0-9]+$'; then
  echo "❌ Недопустимый формат TG_ID. Ожидается числовой Telegram user ID"
  exit 1
fi

# TG_ID обязателен: пустой allowlist + deny-by-default = бот молча игнорирует всех
if [ -z "$TG_ID" ]; then
  echo "❌ TG_ID= обязателен (иначе бот будет глух ко всем)"
  exit 1
fi

# Авто-порт: первый свободный 18790+N (проверяем занятость в override)
if [ -z "$UI_PORT" ]; then
  OVERRIDE_CHECK="docker-compose.override.yml"
  UI_PORT=18790
  while grep -q ":${UI_PORT}:9119" "$OVERRIDE_CHECK" 2>/dev/null; do
    UI_PORT=$((UI_PORT + 1))
  done
fi
TEMPLATE="instances/_template"
TARGET="instances/$NAME"

if [ "$NAME" = "admin" ]; then
  echo "❌ Имя 'admin' зарезервировано"
  exit 1
fi

[ -d "$TARGET" ] && echo "❌ Инстанс '$NAME' уже существует" && exit 1

# Проверяем существование директории шаблона
if [ ! -d "$TEMPLATE/workspace" ]; then
  echo "❌ Директория шаблона не найдена: $TEMPLATE/workspace"
  exit 1
fi

echo "🚀 Создаём инстанс: $FULL_NAME ($NAME)"

mkdir -p "$TARGET/hermes_data"

# Создаём workspace внутри директории инстанса
INSTANCE_WORKSPACE="$TARGET/workspace"
if [ ! -d "$INSTANCE_WORKSPACE" ]; then
    cp -r "$TEMPLATE/workspace/" "$INSTANCE_WORKSPACE"
    rm -rf "$INSTANCE_WORKSPACE/memory"
    echo "  ✅ Workspace создан в instances/$NAME/workspace/"
fi
mkdir -p "$INSTANCE_WORKSPACE/skills" "$INSTANCE_WORKSPACE/memory"

# Персона: Hermes читает SOUL.md из ~/.hermes (=/opt/data), шаблон живёт в workspace
cp "$INSTANCE_WORKSPACE/SOUL.md" "$TARGET/hermes_data/SOUL.md"

# Подставляем переменные в workspace (безопасно для спецсимволов в FULL_NAME)
python3 -c "
import sys, pathlib
name, full_name, ws = sys.argv[1], sys.argv[2], sys.argv[3]
for fname in ['USER.md', 'IDENTITY.md']:
    p = pathlib.Path(ws) / fname
    if p.exists():
        text = p.read_text()
        text = text.replace('{{FULL_NAME}}', full_name).replace('{{NAME}}', name)
        p.write_text(text)
" "$NAME" "$FULL_NAME" "$INSTANCE_WORKSPACE"

# Генерируем ключи
BROKER_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
QUOTA_KEY=$(python3 -c "import secrets; print('quota-${NAME}-' + secrets.token_urlsafe(24))")
GATEWAY_TOKEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
NAME_UPPER=$(echo "$NAME" | tr '[:lower:]' '[:upper:]')

# .env инстанса (compose env_file) — ключи для скиллов и брокера
cat > "$TARGET/.env" << EOF
# Секреты инстанса $NAME — НЕ коммитить в git!
BROKER_URL=http://message-broker:8080
BROKER_KEY=$BROKER_KEY

# Персональные токены:
# YANDEX_OAUTH_TOKEN=
# YANDEX_CALDAV_URL=
# YANDEX_USER=
# YANDEX_APP_PASSWORD=
# GITLAB_TOKEN=
EOF

chmod 600 "$TARGET/.env"

# Hermes конфиг и секреты — кладём в hermes_data/ (маунтится в /opt/data)
cp "$TEMPLATE/hermes_config.yaml.template" "$TARGET/hermes_data/config.yaml"

cat > "$TARGET/hermes_data/.env" << EOF
# Секреты Hermes — НЕ коммитить в git!
TELEGRAM_BOT_TOKEN=$BOT_TOKEN
TELEGRAM_ALLOWED_USERS=${TG_ID}
HERMES_GATEWAY_TOKEN=$GATEWAY_TOKEN
ANTHROPIC_API_KEY=$QUOTA_KEY
# OPENAI_API_KEY=   # для whisper — пробрасывается из глобального .env через compose
EOF
chmod 600 "$TARGET/hermes_data/.env"

# Выставляем владельца — HERMES_UID/HERMES_GID = 1000 (совпадает с chown).
# Используем docker alpine для chown, т.к. deploy user может не иметь прав на chown.
docker run --rm \
    -v "$(pwd)/$TARGET/hermes_data:/data1" \
    -v "$(pwd)/$TARGET/workspace:/data2" \
    alpine chown -R 1000:1000 /data1 /data2

# Добавляем ключи в глобальный .env — без этого quota-proxy не узнает инстанс
if [ ! -f ".env" ]; then
    echo "❌ Корневой .env не найден — QUOTA_KEY не будет зарегистрирован в quota-proxy"
    exit 1
fi
# Гарантия завершающего перевода строки перед append
[ -s .env ] && [ -n "$(tail -c1 .env)" ] && echo >> .env
echo "BROKER_KEY_${NAME_UPPER}=${BROKER_KEY}"  >> .env
echo "QUOTA_KEY_${NAME_UPPER}=${QUOTA_KEY}"    >> .env
echo "QUOTA_LIMIT_${NAME_UPPER}=1000000"       >> .env  # 1M токенов/мес по умолчанию
echo "  ✅ Ключи добавлены в .env"

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
      - ./instances/{name}/hermes_data:/opt/data
      - ./instances/{name}/workspace:/opt/data/workspace
      - ./shared/skills:/shared/skills
      - ./shared/docs:/shared/docs
      - ./shared/compliance-data:/shared/compliance-data:ro
    environment:
      - ANTHROPIC_API_KEY=${{{f"QUOTA_KEY_{NAME_UPPER}"}}}
      - OPENAI_API_KEY=${{OPENAI_API_KEY}}
      - SERVICE_API_KEY=${{SERVICE_API_KEY}}
      - BROKER_URL=http://message-broker:8080
      - BROKER_KEY=${{{f"BROKER_KEY_{NAME_UPPER}"}}}
      - HERMES_UID=1000
      - HERMES_GID=1000
      - HERMES_DASHBOARD=1
    ports:
      - "127.0.0.1:{ui_port}:9119"   # Hermes Dashboard
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

# Валидация итогового compose — ловим YAML-ошибки до деплоя
docker compose config -q && echo "  ✅ docker compose config валиден"

echo ""
echo "✅ Инстанс '$NAME' создан"
echo "   Квота: 1,000,000 токенов/мес (изменить: make set-limit NAME=$NAME LIMIT=500000)"
echo "   Dashboard: http://localhost:$UI_PORT"
echo ""
echo "📋 Далее:"
echo "  1. nano instances/$NAME/.env               — персональные токены"
echo "  2. nano instances/$NAME/hermes_data/SOUL.md  — настроить персонажа (копия из workspace/SOUL.md)"
echo "  3. make deploy"
