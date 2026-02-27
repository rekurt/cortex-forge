#!/usr/bin/env bash
# quota.sh — управление квотами токенов через API (без рестарта)
# Использование:
#   bash scripts/quota.sh report [YYYY-MM]
#   bash scripts/quota.sh set-limit <name> <tokens>
#   bash scripts/quota.sh reset <name> [YYYY-MM]

set -e
[ -f .env ] && source .env 2>/dev/null || true
PROXY_URL="${QUOTA_PROXY_URL:-http://quota-proxy:9090}"
ADMIN_TOKEN="${QUOTA_ADMIN_TOKEN:-changeme}"

CMD="$1"

_curl() {
    curl -sf "$@" -H "Authorization: Bearer $ADMIN_TOKEN"
}

case "$CMD" in
  report)
    MONTH="${2:-}"
    URL="$PROXY_URL/quota/report"
    [ -n "$MONTH" ] && URL="$URL?month=$MONTH"
    _curl "$URL" | python3 -c "
import json, sys
d = json.load(sys.stdin)
print(f\"  📊 Квоты токенов — {d['month']}\")
print()
for u in d['usage']:
    pct  = u.get('used_pct') or 0
    bar  = '█' * min(int(pct / 5), 20)
    lim  = str(u['limit'])
    print(f\"  {u['instance']:<12} {u['total_tokens']:>9,} / {lim:>9} {u['status']}\")
    print(f\"               {bar}\")
    print(f\"               in={u['input_tokens']:,}  out={u['output_tokens']:,}  reqs={u['requests']}\")
print()
lims = d.get('limits', {})
if lims:
    print('  Лимиты:')
    for name, info in sorted(lims.items()):
        print(f\"    {name:<12} {info['limit']:,}  (изменил: {info['updated_by']}, {info['updated_at']})\")
"
    ;;

  set-limit)
    INSTANCE="$2"
    LIMIT="$3"
    [ -z "$INSTANCE" ] || [ -z "$LIMIT" ] && echo "❌ Использование: quota.sh set-limit <name> <tokens>" && exit 1
    RESP=$(_curl -X POST "$PROXY_URL/quota/set-limit" \
        -H "Content-Type: application/json" \
        -d "{\"instance\":\"$INSTANCE\",\"limit\":$LIMIT}")
    echo "$RESP" | python3 -c "
import json, sys
d = json.load(sys.stdin)
if d.get('ok'):
    usage = d.get('current_usage', 0)
    limit = d.get('limit', 0)
    pct = round(usage / limit * 100, 1) if limit > 0 else 0
    status = '❌ exceeded' if limit > 0 and usage >= limit else '⚠️ warning' if pct >= 80 else '✅ ok'
    print(f\"  ✅ Лимит {d['instance']}: {d['limit']:,} токенов/мес\")
    print(f\"     Текущий расход: {usage:,}  {status}\")
else:
    print(f\"  ❌ {d.get('error')}\")
"
    ;;

  reset)
    INSTANCE="$2"
    MONTH="${3:-$(date +%Y-%m)}"
    [ -z "$INSTANCE" ] && echo "❌ Использование: quota.sh reset <name> [YYYY-MM]" && exit 1
    _curl -X POST "$PROXY_URL/quota/reset" \
        -H "Content-Type: application/json" \
        -d "{\"instance\":\"$INSTANCE\",\"month\":\"$MONTH\"}" | python3 -c "
import json, sys
d = json.load(sys.stdin)
print(f\"  ✅ Счётчик {d.get('reset')} сброшен ({d.get('month')})\") if d.get('ok') else print(f\"  ❌ {d.get('error')}\")
"
    ;;

  *)
    echo "Использование:"
    echo "  $0 report [YYYY-MM]              — отчёт по токенам"
    echo "  $0 set-limit <name> <tokens>     — установить квоту (без рестарта)"
    echo "  $0 reset <name> [YYYY-MM]        — сбросить счётчик"
    ;;
esac
