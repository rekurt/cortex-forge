#!/usr/bin/env bash
# Добавляет новый service-инстанс в .env и печатает подсказку для docker-compose
# Использование: make add-service NAME=svc-kyc PORT=8091 SKILLS=compliance,kyc

set -euo pipefail

NAME="${1:-svc-$(date +%s)}"
PORT="${2:-8091}"
SKILLS="${3:-compliance}"

echo "🔧 Добавляем service-инстанс: $NAME (порт $PORT, скиллы: $SKILLS)"

# Генерируем уникальный API ключ
KEY=$(python3 -c "import secrets; print('svc-' + secrets.token_urlsafe(24))")

# Верхний регистр для имени переменной
NAME_UPPER=$(echo "$NAME" | tr '[:lower:]-' '[:upper:]_')

ENV_VAR="SERVICE_API_KEY_${NAME_UPPER}"

# Добавляем в .env если такой переменной ещё нет
if grep -q "^${ENV_VAR}=" .env 2>/dev/null; then
  echo "⚠️  ${ENV_VAR} уже есть в .env, пропускаю генерацию ключа"
else
  echo "${ENV_VAR}=${KEY}" >> .env
  echo "✅ Ключ добавлен в .env: ${ENV_VAR}"
fi

echo ""
echo "📝 Добавь в docker-compose.yml следующий сервис:"
echo "────────────────────────────────────────────────"
cat <<EOF
  ${NAME}:
    build: ./service-agent
    container_name: corp-${NAME}
    restart: unless-stopped
    env_file: .env
    environment:
      - SERVICE_PORT=${PORT}
      - SERVICE_API_KEY=\${${ENV_VAR}}
      - SKILL_TIMEOUT=150
      - MAX_CONCURRENT_TASKS=5
    volumes:
      - ${NAME}-data:/data
      - ./service-agent/skills:/app/skills:ro
    ports:
      - "127.0.0.1:${PORT}:${PORT}"
    networks:
      - corp-internal
      - corp-services
    security_opt:
      - no-new-privileges:true
    deploy:
      resources:
        limits:
          cpus: "2.0"
          memory: 1G
    healthcheck:
      test: ["CMD", "python3", "-c",
             "import urllib.request; urllib.request.urlopen('http://localhost:${PORT}/v1/health', timeout=3)"]
      interval: 30s
      timeout: 5s
      retries: 3

volumes:
  ${NAME}-data:
    driver: local
EOF
echo "────────────────────────────────────────────────"
echo ""
echo "Затем: docker compose up -d --build ${NAME}"
