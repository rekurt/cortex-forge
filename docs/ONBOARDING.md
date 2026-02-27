# ONBOARDING.md — Добавление нового сотрудника

## Шаги

### 1. Сотрудник создаёт Telegram-бота

1. Написать @BotFather в Telegram
2. `/newbot` → придумать имя и username
3. Получить токен вида `7000000000:AAxxxx`
4. Отдать токен администратору

### 2. Администратор запускает скрипт

```bash
make add-user \
  NAME=dmitry \
  BOT_TOKEN=7000000000:AAxxxx \
  FULL_NAME="Дмитрий Смирнов" \
  TG_ID=987654321  # Telegram ID сотрудника
```

### 3. Заполнить секреты сотрудника

```bash
nano instances/dmitry/.env
```

Добавить:
- `YANDEX_OAUTH_TOKEN` — для почты/календаря
- `YANDEX_CALDAV_URL`, `YANDEX_USER`, `YANDEX_APP_PASSWORD` — для Яндекс Календаря
- `GITLAB_TOKEN` — если нужен доступ к GitLab
- Прочие персональные API-ключи

### 4. (Опционально) Настроить персонажа

```bash
# Выбрать имя, стиль общения
nano instances/dmitry/workspace/SOUL.md
nano instances/dmitry/workspace/IDENTITY.md
```

### 5. Задеплоить

```bash
make deploy
# или перезапустить только этого:
make restart NAME=dmitry
```

### 6. Первый запуск

Сотрудник пишет боту любое сообщение. Готово.

---

## Где взять Telegram ID

Сотрудник пишет @userinfobot в Telegram — бот отвечает его ID.

---

## Чеклист онбординга

- [ ] Бот создан в @BotFather, токен получен
- [ ] `make add-user` выполнен
- [ ] `instances/{name}/.env` заполнен
- [ ] Персонаж настроен (SOUL.md / IDENTITY.md)
- [ ] `make deploy` выполнен
- [ ] Сотрудник написал боту первое сообщение
- [ ] Сотрудник добавил корпоративные инструкции (кому писать, какие задачи, etc.)
