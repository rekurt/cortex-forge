#!/usr/bin/env bash
# fix-permissions.sh — выставляет правильные права на секретные файлы
set -e

echo "🔒 Исправляем права файлов..."

# .env с секретами — только владелец читает
[ -f .env ] && chmod 600 .env && echo "  ✅ .env → 600"

# Секреты инстансов
for f in instances/*/.env instances/*/hermes_data/config.yaml instances/*/hermes_data/.env; do
    [ -f "$f" ] && chmod 600 "$f" && echo "  ✅ $f → 600"
done

# Hermes-данные — владелец 1000:1000 (HERMES_UID/GID), иначе агент не прочитает свой конфиг
for d in instances/*/hermes_data; do
    if [ -d "$d" ]; then
        chown -R 1000:1000 "$d" 2>/dev/null || sudo chown -R 1000:1000 "$d" || true
        echo "  ✅ $d → 1000:1000"
    fi
done

# Скрипты — исполняемые
for f in scripts/*.sh; do
    [ -f "$f" ] && chmod 755 "$f" && echo "  ✅ $f → 755"
done

# Директории инстансов — только владелец
for d in instances/*/; do
    [ -d "$d" ] && chmod 700 "$d" && echo "  ✅ $d → 700"
done

echo ""
echo "✅ Готово. Запусти make security-check для проверки."
