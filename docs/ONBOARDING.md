# ONBOARDING.md — Добавление нового сотрудника

## Предварительное условие

Admin-инстанс (Приор) должен быть уже запущен и работать. Если нет — см. [SETUP.md](SETUP.md).

---

## Шаги

### 1. Сотрудник создаёт Telegram-бота

1. Написать [@BotFather](https://t.me/BotFather) в Telegram
2. `/newbot` → придумать имя и username
3. Получить токен вида `7000000000:AAxxxx`
4. Отдать токен администратору
5. Узнать свой Telegram ID через [@userinfobot](https://t.me/userinfobot)

### 2. Администратор запускает скрипт

```bash
make add-user \
  NAME=dmitry \
  BOT_TOKEN=7000000000:AAxxxx \
  FULL_NAME="Дмитрий Смирнов" \
  TG_ID=987654321
```

Скрипт автоматически:
- Создаёт директорию `instances/dmitry/` из шаблона
- Генерирует уникальные `BROKER_KEY` и `QUOTA_KEY`
- Добавляет ключи и лимит (1М токенов/мес) в глобальный `.env`
- Выводит YAML-блок для вставки в `docker-compose.yml`

### 3. Добавить YAML-блок в docker-compose.yml

Скрипт выводит готовый блок — скопировать в раздел `services:` файла `docker-compose.yml`.

### 4. Заполнить личные секреты

```bash
nano instances/dmitry/.env
chmod 600 instances/dmitry/.env
```

Опциональные ключи:

| Ключ | Описание |
|---|---|
| `YANDEX_OAUTH_TOKEN` | Яндекс OAuth для почты / Трекера |
| `YANDEX_CALDAV_URL` | CalDAV URL Яндекс Календаря |
| `YANDEX_USER` | Логин Яндекс |
| `YANDEX_APP_PASSWORD` | Пароль приложения Яндекс |
| `GITLAB_TOKEN` | GitLab Personal Access Token |

### 5. (Опционально) Настроить персонажа

```bash
nano instances/dmitry/workspace/SOUL.md      # стиль общения
nano instances/dmitry/workspace/IDENTITY.md  # имя, emoji, роль
nano instances/dmitry/workspace/USER.md      # кто этот сотрудник
```

Подробнее — [PERSONAS.md](PERSONAS.md).

### 6. Задеплоить

```bash
make deploy
# или перезапустить только этого инстанса:
make restart NAME=dmitry
```

### 7. Первый запуск

Сотрудник пишет боту любое сообщение — бот готов к работе.

---

## Чеклист онбординга

- [ ] Бот создан в @BotFather, токен получен
- [ ] Telegram ID сотрудника получен через @userinfobot
- [ ] `make add-user` выполнен без ошибок
- [ ] YAML-блок добавлен в `docker-compose.yml`
- [ ] `instances/{name}/.env` заполнен, права `600`
- [ ] Персонаж настроен (`SOUL.md` / `IDENTITY.md`)
- [ ] `make deploy` выполнен, контейнер `healthy`
- [ ] Сотрудник написал боту первое сообщение
- [ ] Установлена квота: `make set-limit NAME=dmitry LIMIT=500000`

---

## Удаление сотрудника

```bash
make remove-user NAME=dmitry
```

Скрипт:
1. Останавливает и удаляет контейнер
2. **Архивирует воркспейс** в `backups/dmitry-YYYYMMDD.tar.gz`
3. Удаляет `instances/dmitry/`
4. Очищает ключи из глобального `.env`
5. Удаляет блок из `docker-compose.yml`

---

## Управление квотами

```bash
make quota-report                    # отчёт за текущий месяц
make set-limit NAME=dmitry LIMIT=1000000  # изменить лимит (без рестарта)
make quota-reset NAME=dmitry         # сбросить счётчик
```
