.PHONY: add-user remove-user deploy restart logs backup status quota-report quota-reset set-limit

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
