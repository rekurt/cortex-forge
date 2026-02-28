#!/usr/bin/env bash
# corp-docs/search.sh — поиск по корпоративной базе знаний
# Usage: bash search.sh "запрос" [коллекция]

QUERY="${1:-}"
COLLECTION="${2:-}"
DOCS_DIR="/shared/docs"
QMD_INDEX="$DOCS_DIR/.qmd-index"
QMD_BIN="$HOME/.local/bin/qmd"

if [ -z "$QUERY" ]; then
  echo "Usage: bash search.sh \"запрос\" [коллекция]"
  exit 1
fi

if [ ! -f "$QMD_BIN" ]; then
  echo "QMD не установлен. Устанавливаю..."
  npm install -g @tobilu/qmd --prefix "$HOME/.local" --silent
fi

# Инициализировать коллекции если нужно
if [ ! -f "$QMD_INDEX/collections.json" ] 2>/dev/null; then
  export XDG_CACHE_HOME="$DOCS_DIR/.qmd-index"
  "$QMD_BIN" collection add "$DOCS_DIR/common" --name common 2>/dev/null
  "$QMD_BIN" collection add "$DOCS_DIR/user-1" --name user-1 2>/dev/null
  "$QMD_BIN" collection add "$DOCS_DIR/user-3" --name user-3 2>/dev/null
  "$QMD_BIN" collection add "$DOCS_DIR/user-4" --name user-4 2>/dev/null
  "$QMD_BIN" embed 2>/dev/null
fi

export XDG_CACHE_HOME="$DOCS_DIR/.qmd-index"

if [ -n "$COLLECTION" ]; then
  "$QMD_BIN" search "$QUERY" -c "$COLLECTION" -n 10
else
  "$QMD_BIN" search "$QUERY" -n 10
fi
