.PHONY: add-user remove-user deploy restart logs backup status quota-report quota-reset set-limit security-check monitor monitor-alerts add-service service-health service-skills install-hooks admin-overview

# ── Управление инстансами ──────────────────────────────────────────────────

# make add-user NAME=alexey BOT_TOKEN=7xxx FULL_NAME="Алексей Михайлюк" TG_ID=123456789
add-user:
	@[ -n "$(NAME)" ] || (echo "❌ NAME= обязателен"; exit 1)
	@[ -n "$(BOT_TOKEN)" ] || (echo "❌ BOT_TOKEN= обязателен"; exit 1)
	@bash scripts/add-user.sh "$(NAME)" "$(BOT_TOKEN)" "$(FULL_NAME)" "$(TG_ID)"

# make remove-user NAME=alexey
remove-user:
	@[ -n "$(NAME)" ] || (echo "❌ NAME= обязателен"; exit 1)
	@bash scripts/remove-user.sh "$(NAME)"

# ── Деплой ────────────────────────────────────────────────────────────────

deploy:
	docker compose up -d --build
	@echo "✅ Все инстансы запущены"

# make install-hooks — автоперезапуск контейнеров при git pull
install-hooks:
	@bash scripts/install-hooks.sh

# make restart NAME=alexey
restart:
	@[ -n "$(NAME)" ] || (echo "❌ NAME= обязателен"; exit 1)
	docker compose restart assistant-$(NAME)

# make logs NAME=alexey
logs:
	@[ -n "$(NAME)" ] || (echo "❌ NAME= обязателен"; exit 1)
	docker compose logs -f assistant-$(NAME)

status:
	docker compose ps

backup:
	@bash scripts/backup.sh

# ── Безопасность ───────────────────────────────────────────────────────────

# Проверка базовых требований безопасности
security-check:
	@echo "🔒 Проверка безопасности..."
	@[ -f .env ] && stat -c "%a" .env | grep -qE "^6[04]0$$" \
	  && echo "  ✅ .env: права 600/640" \
	  || echo "  ❌ .env: исправь права: chmod 600 .env"
	@find instances -name ".env" | while read f; do \
	  mode=$$(stat -c "%a" $$f); \
	  echo $$mode | grep -qE "^6[04]0$$" \
	    && echo "  ✅ $$f: $${mode}" \
	    || echo "  ❌ $$f: chmod 600 $$f"; \
	done
	@grep -q "ANTHROPIC_API_KEY=sk-" .env 2>/dev/null \
	  && echo "  ✅ ANTHROPIC_API_KEY задан" \
	  || echo "  ❌ ANTHROPIC_API_KEY не задан в .env"
	@grep -q "^QUOTA_ADMIN_TOKEN=.\{16\}" .env 2>/dev/null \
	  && echo "  ✅ QUOTA_ADMIN_TOKEN достаточно длинный" \
	  || echo "  ❌ QUOTA_ADMIN_TOKEN слишком короткий или не задан"
	@! git ls-files .env 2>/dev/null | grep -q ".env" \
	  && echo "  ✅ .env не в git" \
	  || echo "  ❌ .env попал в git! git rm --cached .env"
	@echo "  ℹ️  Проверь: docker compose ps (все контейнеры healthy?)"

# ── Квоты токенов ─────────────────────────────────────────────────────────

# Отчёт по использованию: make quota-report  /  make quota-report MONTH=2026-03
quota-report:
	@bash scripts/quota.sh report $(MONTH)

# Сбросить счётчик: make quota-reset NAME=alexey
quota-reset:
	@[ -n "$(NAME)" ] || (echo "❌ NAME= обязателен"; exit 1)
	@bash scripts/quota.sh reset $(NAME)

# Установить лимит БЕЗ рестарта: make set-limit NAME=alexey LIMIT=500000
set-limit:
	@[ -n "$(NAME)" ] || (echo "❌ NAME= обязателен"; exit 1)
	@[ -n "$(LIMIT)" ] || (echo "❌ LIMIT= обязателен"; exit 1)
	@bash scripts/quota.sh set-limit $(NAME) $(LIMIT)

# ── Resource Monitor ────────────────────────────────────────────────────────

monitor: ## Показать текущие метрики ресурсов
	@bash scripts/monitor.sh metrics

monitor-alerts: ## Показать активные алерты
	@bash scripts/monitor.sh alerts/active

# ── Service Agent ───────────────────────────────────────────────────────────

# make add-service NAME=svc-kyc PORT=8091 SKILLS=compliance,kyc
add-service: ## Добавить реплицированный service-инстанс (NAME=x PORT=y SKILLS=z)
	@[ -n "$(NAME)" ] || (echo "❌ NAME= обязателен"; exit 1)
	@bash scripts/add-service.sh "$(NAME)" "$(PORT)" "$(SKILLS)"

service-health: ## Проверить health service-инстанса
	@curl -sf http://localhost:8090/v1/health | python3 -m json.tool

service-skills: ## Показать доступные скиллы service-инстанса
	@curl -sf -H "Authorization: Bearer $${SERVICE_API_KEY}" http://localhost:8090/v1/skills | python3 -m json.tool

admin-overview: ## Сводка admin-dashboard: квоты + метрики + алерты
	@curl -sf -X POST http://localhost:8090/v1/run \
	  -H "Authorization: Bearer $${SERVICE_API_KEY}" \
	  -H "Content-Type: application/json" \
	  -d '{"skill": "admin-dashboard", "caller": "makefile", "params": {"action": "overview"}}' \
	  | python3 -m json.tool
