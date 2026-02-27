#!/usr/bin/env bash
# quota.sh — управление квотами токенов
# Использование:
#   bash scripts/quota.sh report              — отчёт по всем за текущий месяц
#   bash scripts/quota.sh report 2026-03      — за конкретный месяц
#   bash scripts/quota.sh reset nikita        — сбросить счётчик Никиты
#   bash scripts/quota.sh set-limit nikita 500000  — установить лимит

set -e
source .env 2>/dev/null || true
PROXY_URL="${QUOTA_PROXY_URL:-http://localhost:9090}"
ADMIN_TOKEN="${QUOTA_ADMIN_TOKEN:-changeme}"

CMD="$1"

case "$CMD" in
  report)
    MONTH="${2:-}"
    URL="$PROXY_URL/quota/report"
    [ -n "$MONTH" ] && URL="$URL?month=$MONTH"
    echo "📊 Отчёт по токенам$([ -n "$MONTH" ] && echo " ($MONTH)" || echo " (текущий месяц)"):"
    curl -sf "$URL" -H "Authorization: Bearer $ADMIN_TOKEN" | \
      python3 -c "
import json, sys
d = json.load(sys.stdin)
print(f\"  Месяц: {d['month']}\")
print()
for u in d['usage']:
    bar = '█' * int((u.get('used_pct') or 0) / 5)
    print(f\"  {u['instance']:<12} {u['total_tokens']:>8,} / {str(u['limit']):>9} токенов  {u['status']}  {bar}\")
    print(f\"               in={u['input_tokens']:,}  out={u['output_tokens']:,}  reqs={u['requests']}\")
print()
"
    ;;

  reset)
    INSTANCE="$2"
    [ -z "$INSTANCE" ] && echo "❌ Укажи имя: quota.sh reset <name>" && exit 1
    curl -sf "$PROXY_URL/quota/reset?instance=$INSTANCE" \
      -H "Authorization: Bearer $ADMIN_TOKEN" | python3 -m json.tool
    echo "✅ Счётчик $INSTANCE сброшен"
    ;;

  set-limit)
    INSTANCE="$2"
    LIMIT="$3"
    [ -z "$INSTANCE" ] || [ -z "$LIMIT" ] && echo "❌ Использование: quota.sh set-limit <name> <tokens>" && exit 1
    NAME_UPPER=$(echo "$INSTANCE" | tr '[:lower:]' '[:upper:]')
    # Обновляем в .env
    if grep -q "QUOTA_LIMIT_${NAME_UPPER}" .env 2>/dev/null; then
      sed -i "s/^QUOTA_LIMIT_${NAME_UPPER}=.*/QUOTA_LIMIT_${NAME_UPPER}=$LIMIT/" .env
    else
      echo "QUOTA_LIMIT_${NAME_UPPER}=$LIMIT" >> .env
    fi
    echo "✅ Лимит для $INSTANCE установлен: $LIMIT токенов/мес"
    echo "💡 Примени: make restart NAME=quota-proxy  (или make deploy)"
    ;;

  *)
    echo "Использование:"
    echo "  $0 report [YYYY-MM]          — отчёт по использованию"
    echo "  $0 reset <instance>          — сбросить счётчик"
    echo "  $0 set-limit <instance> <N>  — установить лимит токенов/мес"
    ;;
esac
