#!/usr/bin/env bash
# provision-hermes-data.sh — гарантирует hermes_data/ для инстансов:
# каталог, .env с Hermes-секретами, SOUL.md, права 1000:1000 (HERMES_UID/GID).
# Использование: bash scripts/provision-hermes-data.sh [NAME ...]   (без аргументов — все)
# Вызывается из `make bootstrap`; идемпотентно.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
INSTANCES="$ROOT/instances"

provision() {
  local NAME="$1" DIR="$INSTANCES/$NAME"
  [ -d "$DIR" ] || { echo "❌ $DIR не найден"; exit 1; }
  mkdir -p "$DIR/hermes_data/ssh"

  # .env для Hermes — из instance .env (поддержка старых и новых имён переменных)
  if [ ! -f "$DIR/hermes_data/.env" ] && [ -f "$DIR/.env" ]; then
    tg_token=$(grep -E '^TELEGRAM_BOT_TOKEN=' "$DIR/.env" | head -1 | cut -d= -f2-)
    tg_users=$(grep -E '^TELEGRAM_ALLOWED_USERS=' "$DIR/.env" | head -1 | cut -d= -f2-)
    [ -z "$tg_users" ] && tg_users=$(grep -E '^TELEGRAM_ALLOW_FROM=' "$DIR/.env" | head -1 | cut -d= -f2-)
    gw=$(grep -E '^HERMES_GATEWAY_TOKEN=' "$DIR/.env" | head -1 | cut -d= -f2-)
    [ -z "$gw" ] && gw=$(grep -E '^GATEWAY_TOKEN=' "$DIR/.env" | head -1 | cut -d= -f2-)
    ak=$(grep -E '^ANTHROPIC_API_KEY=' "$DIR/.env" | head -1 | cut -d= -f2-)
    # fallback: root .env → ANTHROPIC_API_KEY (admin), затем QUOTA_KEY_<NAME> (user)
    if [ -z "$ak" ] && [ -f "$ROOT/.env" ]; then
      ak=$(grep -E '^ANTHROPIC_API_KEY=' "$ROOT/.env" | head -1 | cut -d= -f2-)
      [ -z "$ak" ] && ak=$(grep -E "^QUOTA_KEY_$(echo "$NAME" | tr '[:lower:]' '[:upper:]')=" "$ROOT/.env" | head -1 | cut -d= -f2-)
    fi
    {
      echo "TELEGRAM_BOT_TOKEN=${tg_token:-}"
      echo "TELEGRAM_ALLOWED_USERS=${tg_users:-}"
      echo "HERMES_GATEWAY_TOKEN=${gw:-}"
      echo "ANTHROPIC_API_KEY=${ak:-}"
      echo "# OPENAI_API_KEY=  # для voice.stt.provider: openai"
    } > "$DIR/hermes_data/.env"
    chmod 600 "$DIR/hermes_data/.env"
    echo "  [$NAME] hermes_data/.env создан"
  fi

  # Персона: Hermes читает SOUL.md из ~/.hermes (=/opt/data), шаблон живёт в workspace
  if [ -f "$DIR/workspace/SOUL.md" ] && [ ! -f "$DIR/hermes_data/SOUL.md" ]; then
    cp "$DIR/workspace/SOUL.md" "$DIR/hermes_data/SOUL.md"
    echo "  [$NAME] SOUL.md скопирован в hermes_data/"
  fi

  # Права: HERMES_UID/GID=1000 — иначе s6-процесс не сможет писать в свой home
  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    docker run --rm -v "$DIR/hermes_data:/data" alpine chown -R 1000:1000 /data
  else
    chown -R 1000:1000 "$DIR/hermes_data" 2>/dev/null \
      || sudo chown -R 1000:1000 "$DIR/hermes_data"
  fi
  echo "  [$NAME] ✅ provisioned"
}

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
