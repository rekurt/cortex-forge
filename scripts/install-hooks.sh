#!/usr/bin/env bash
# Устанавливает git-хуки для автоматического деплоя при git pull
set -e

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOKS_DIR="$REPO_ROOT/.git/hooks"
SCRIPTS_DIR="$REPO_ROOT/scripts"

echo "📎 Устанавливаю git-хуки..."

cp "$SCRIPTS_DIR/post-merge-hook.sh" "$HOOKS_DIR/post-merge"
chmod +x "$HOOKS_DIR/post-merge"

echo "  ✅ post-merge → .git/hooks/post-merge"
echo ""
echo "Теперь 'git pull' будет автоматически пересобирать и перезапускать изменившиеся сервисы."
