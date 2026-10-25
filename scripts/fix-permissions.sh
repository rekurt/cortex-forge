#!/usr/bin/env bash
# fix-permissions.sh — выставляет правильные права на секретные файлы и воркспейсы
set -e

echo "🔒 Исправляем права файлов..."

# .env с секретами — только владелец читает
[ -f .env ] && chmod 600 .env && echo "  ✅ .env → 600"

# Секреты инстансов
for f in instances/*/.env instances/*/hermes_data/config.yaml instances/*/hermes_data/.env; do
    [ -f "$f" ] && chmod 600 "$f" && echo "  ✅ $f → 600"
done

# Hermes-данные и воркспейсы — владелец 1000:1000 (HERMES_UID/GID)
for d in instances/*/hermes_data instances/*/workspace; do
    [ "$d" = "instances/_template/workspace" ] && continue
    if [ -d "$d" ]; then
        if chown -R 1000:1000 "$d" 2>/dev/null || sudo -n chown -R 1000:1000 "$d" 2>/dev/null; then
            echo "  ✅ $d → 1000:1000"
        else
            echo "  ⚠️  $d: не удалось выставить chown 1000:1000 (запусти под root или через make bootstrap)"
        fi
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
