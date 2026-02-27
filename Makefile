.PHONY: add-user remove-user deploy restart logs backup status

# Добавить нового сотрудника
# Использование: make add-user NAME=alexey BOT_TOKEN=7xxx:yyy FULL_NAME="Алексей Михайлюк" TG_ID=123456789
add-user:
	@[ -n "$(NAME)" ] || (echo "❌ Укажи NAME=имя"; exit 1)
	@[ -n "$(BOT_TOKEN)" ] || (echo "❌ Укажи BOT_TOKEN=токен"; exit 1)
	@bash scripts/add-user.sh "$(NAME)" "$(BOT_TOKEN)" "$(FULL_NAME)" "$(TG_ID)"

# Удалить инстанс сотрудника
# Использование: make remove-user NAME=alexey
remove-user:
	@[ -n "$(NAME)" ] || (echo "❌ Укажи NAME=имя"; exit 1)
	@bash scripts/remove-user.sh "$(NAME)"

# Развернуть / обновить все инстансы
deploy:
	docker compose up -d --build
	@echo "✅ Все инстансы запущены"

# Перезапустить конкретного пользователя
# Использование: make restart NAME=alexey
restart:
	@[ -n "$(NAME)" ] || (echo "❌ Укажи NAME=имя"; exit 1)
	docker compose restart assistant-$(NAME)

# Логи конкретного пользователя
# Использование: make logs NAME=alexey
logs:
	@[ -n "$(NAME)" ] || (echo "❌ Укажи NAME=имя"; exit 1)
	docker compose logs -f assistant-$(NAME)

# Статус всех инстансов
status:
	docker compose ps

# Бекап всех воркспейсов
backup:
	@bash scripts/backup.sh
