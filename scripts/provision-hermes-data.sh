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
  if [ ! -d "$DIR" ] || [ -L "$DIR" ]; then
    echo "⚠️  $DIR не найден или является симлинком — пропускаем"
    return 0
  fi
  if [ -L "$DIR/hermes_data" ] || [ -L "$DIR/workspace" ]; then
    echo "❌ [$NAME] hermes_data или workspace является симлинком — пропускаем (защита от symlink-атаки)"
    return 0
  fi
  mkdir -p "$DIR/hermes_data/ssh"

  # Конфиг Hermes для user-инстансов (у admin свой instances/admin/config.yaml через bind-mount)
  if [ "$NAME" != "admin" ] && [ ! -e "$DIR/hermes_data/config.yaml" ] && [ ! -L "$DIR/hermes_data/config.yaml" ] && [ -f "$TEMPLATE/hermes_config.yaml.template" ]; then
    cp "$TEMPLATE/hermes_config.yaml.template" "$DIR/hermes_data/config.yaml"
    chmod 600 "$DIR/hermes_data/config.yaml"
    echo "  [$NAME] hermes_data/config.yaml создан из шаблона"
  fi

  # .env для Hermes — из instance .env (отклоняем симлинки; || true защищает от pipefail)
  if [ ! -e "$DIR/hermes_data/.env" ] && [ ! -L "$DIR/hermes_data/.env" ] && [ -f "$DIR/.env" ] && [ ! -L "$DIR/.env" ]; then
    local tg_token tg_users gw ak oai name_upper
    name_upper=$(echo "$NAME" | tr '[:lower:]-' '[:upper:]_')
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

  # Персона: Hermes читает SOUL.md из ~/.hermes (=/opt/data), источником истины служит workspace/SOUL.md.
  # Защита от symlink-атаки (O_NOFOLLOW): отказ при симлинках в источнике или приёмнике.
  if [ -L "$DIR/workspace/SOUL.md" ] || [ -L "$DIR/hermes_data/SOUL.md" ]; then
    echo "  ⚠️  [$NAME] SOUL.md является симлинком — синхронизация отклонена"
  elif [ -f "$DIR/workspace/SOUL.md" ]; then
    python3 - "$DIR/workspace/SOUL.md" "$DIR/hermes_data/SOUL.md" "$NAME" << 'PYEOF'
import os, stat, sys

src, dst, name = sys.argv[1], sys.argv[2], sys.argv[3]
nofollow = getattr(os, "O_NOFOLLOW", 0)
fd_in = os.open(src, os.O_RDONLY | nofollow)
try:
    st = os.fstat(fd_in)
    if not stat.S_ISREG(st.st_mode):
        sys.exit(0)
    with os.fdopen(fd_in, "rb") as f_in:
        data = f_in.read()
        fd_in = -1
finally:
    if fd_in >= 0:
        os.close(fd_in)

existing = None
if os.path.lexists(dst):
    fd_old = os.open(dst, os.O_RDONLY | nofollow)
    try:
        with os.fdopen(fd_old, "rb") as f_old:
            existing = f_old.read()
            fd_old = -1
    finally:
        if fd_old >= 0:
            os.close(fd_old)

if existing != data:
    tmp = dst + ".tmp"
    if os.path.lexists(tmp):
        os.unlink(tmp)
    fd_out = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow, 0o600)
    with os.fdopen(fd_out, "wb") as f_out:
        f_out.write(data)
    os.replace(tmp, dst)
    print(f"  [{name}] SOUL.md синхронизирован в hermes_data/")
PYEOF
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
