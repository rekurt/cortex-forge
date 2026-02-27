#!/usr/bin/env bash
# backup.sh — бекап воркспейсов всех инстансов в git
# Запускается через cron или make backup

set -e
TODAY=$(date +%Y-%m-%d)
CHANGED=0

echo "🔄 Бекап воркспейсов ($TODAY)..."

cd "$(dirname "$0")/.."

for instance_dir in instances/*/; do
    name=$(basename "$instance_dir")
    [ "$name" = "_template" ] && continue

    ws="$instance_dir/workspace"
    [ -d "$ws" ] || continue

    # Добавляем файлы воркспейса (кроме .venv, __pycache__)
    git add "$ws" 2>/dev/null || true
    CHANGED=$((CHANGED + 1))
done

if git diff --staged --quiet; then
    echo "✅ Изменений нет"
    exit 0
fi

FILES=$(git diff --staged --name-only | wc -l)
git commit -m "backup: авто-бекап $TODAY ($FILES файлов)" --quiet

if ! git push --quiet 2>&1; then
    echo "❌ Ошибка git push! Бекап закоммичен локально, но не отправлен на remote." >&2
    echo "   Проверь: git log -1 && git push" >&2
    exit 1
fi

echo "✅ Запушено: $FILES файлов"
