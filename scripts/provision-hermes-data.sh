#!/usr/bin/env bash
# provision-hermes-data.sh — гарантирует hermes_data/ для инстансов:
# каталог, config.yaml (для user-инстансов), .env с Hermes-секретами,
# SOUL.md, права 1000:1000 (HERMES_UID/GID).
# Использование: bash scripts/provision-hermes-data.sh [NAME ...]   (без аргументов — все)
# Вызывается из `make bootstrap` и `make deploy`; идемпотентно.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
INSTANCES="$ROOT/instances"
TEMPLATE="$INSTANCES/_template"

provision() {
  local NAME="$1"
  local DIR="$INSTANCES/$NAME"
  if [ ! -d "$DIR" ]; then
    echo "⚠️  $DIR не найден — пропускаем"
    return 0
  fi
  mkdir -p "$DIR/hermes_data/ssh"

  # Конфиг Hermes для user-инстансов (у admin свой instances/admin/config.yaml через bind-mount)
  if [ "$NAME" != "admin" ] && [ ! -f "$DIR/hermes_data/config.yaml" ] && [ -f "$TEMPLATE/hermes_config.yaml.template" ]; then
    cp "$TEMPLATE/hermes_config.yaml.template" "$DIR/hermes_data/config.yaml"
    chmod 600 "$DIR/hermes_data/config.yaml"
    echo "  [$NAME] hermes_data/config.yaml создан из шаблона"
  fi

  # .env для Hermes — из instance .env (поддержка старых и новых имён переменных; || true защищает от pipefail)
  if [ ! -f "$DIR/hermes_data/.env" ] && [ -f "$DIR/.env" ]; then
    local tg_token tg_users gw ak oai name_upper
    name_upper=$(echo "$NAME" | tr '[:lower:]' '[:upper:]')
    tg_token=$(grep -E '^TELEGRAM_BOT_TOKEN=' "$DIR/.env" | head -1 | cut -d= -f2- || true)
    tg_users=$(grep -E '^TELEGRAM_ALLOWED_USERS=' "$DIR/.env" | head -1 | cut -d= -f2- || true)
    [ -z "$tg_users" ] && tg_users=$(grep -E '^TELEGRAM_ALLOW_FROM=' "$DIR/.env" | head -1 | cut -d= -f2- || true)
    gw=$(grep -E '^HERMES_GATEWAY_TOKEN=' "$DIR/.env" | head -1 | cut -d= -f2- || true)
    [ -z "$gw" ] && gw=$(grep -E '^GATEWAY_TOKEN=' "$DIR/.env" | head -1 | cut -d= -f2- || true)
    ak=$(grep -E '^ANTHROPIC_API_KEY=' "$DIR/.env" | head -1 | cut -d= -f2- || true)
    oai=$(grep -E '^OPENAI_API_KEY=' "$DIR/.env" | head -1 | cut -d= -f2- || true)

    # Строгое разделение ключей: admin берёт реальный ANTHROPIC_API_KEY, user — только QUOTA_KEY_<NAME>
    if [ -z "$ak" ] && [ -f "$ROOT/.env" ]; then
      if [ "$NAME" = "admin" ]; then
        ak=$(grep -E '^ANTHROPIC_API_KEY=' "$ROOT/.env" | head -1 | cut -d= -f2- || true)
      else
        ak=$(grep -E "^QUOTA_KEY_${name_upper}=" "$ROOT/.env" | head -1 | cut -d= -f2- || true)
      fi
    fi
    if [ -z "$oai" ] && [ -f "$ROOT/.env" ]; then
      oai=$(grep -E '^OPENAI_API_KEY=' "$ROOT/.env" | head -1 | cut -d= -f2- || true)
    fi

    {
      echo "TELEGRAM_BOT_TOKEN=${tg_token:-}"
      echo "TELEGRAM_ALLOWED_USERS=${tg_users:-}"
      echo "HERMES_GATEWAY_TOKEN=${gw:-}"
      echo "ANTHROPIC_API_KEY=${ak:-}"
      if [ -n "${oai:-}" ]; then
        echo "OPENAI_API_KEY=${oai}"
      else
        echo "# OPENAI_API_KEY=  # для voice.stt.provider: openai"
      fi
    } > "$DIR/hermes_data/.env"
    chmod 600 "$DIR/hermes_data/.env"
    echo "  [$NAME] hermes_data/.env создан"
  fi

  # Персона: Hermes читает SOUL.md из ~/.hermes (=/opt/data), источником истины служит workspace/SOUL.md
  if [ -f "$DIR/workspace/SOUL.md" ]; then
    if [ ! -f "$DIR/hermes_data/SOUL.md" ] || ! diff -q "$DIR/workspace/SOUL.md" "$DIR/hermes_data/SOUL.md" >/dev/null 2>&1; then
      cp "$DIR/workspace/SOUL.md" "$DIR/hermes_data/SOUL.md"
      echo "  [$NAME] SOUL.md синхронизирован в hermes_data/"
    fi
  fi

  # Права: HERMES_UID/GID=1000 — иначе s6-процесс не сможет писать в свой home
  if chown -R 1000:1000 "$DIR/hermes_data" 2>/dev/null; then
    :
  elif command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    docker run --rm -v "$DIR/hermes_data:/data" alpine chown -R 1000:1000 /data
  elif sudo -n chown -R 1000:1000 "$DIR/hermes_data" 2>/dev/null; then
    :
  else
    echo "  ⚠️  [$NAME] не удалось выставить 1000:1000 на $DIR/hermes_data (нужен root или работающий Docker)"
  fi
  echo "  [$NAME] ✅ provisioned"
}

shopt -s nullglob
if [ $# -eq 0 ]; then
  for d in "$INSTANCES"/*/; do
    n=$(basename "$d")
    [ "$n" = "_template" ] && continue
    provision "$n"
  done
else
  for n in "$@"; do
    provision "$n"
  done
fi
