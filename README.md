# 🤖 corp-assistant

Корпоративная инфраструктура AI-ассистентов на базе OpenClaw.

Каждый сотрудник получает **своего персонажа** — изолированный инстанс с уникальной личностью, отдельными данными и своим Telegram-ботом.

---

## Быстрый старт

```bash
# 1. Клонировать репо на сервер
git clone https://github.com/rekurt/corp-assistant.git
cd corp-assistant

# 2. Настроить глобальный конфиг
cp .env.example .env
# Заполнить ANTHROPIC_API_KEY в .env

# 3. Добавить первого сотрудника
make add-user NAME=alexey BOT_TOKEN=7xxx:yyy FULL_NAME="Алексей Михайлюк" TG_ID=123456789

# 4. Заполнить личные секреты сотрудника
nano instances/alexey/.env

# 5. Настроить персонажа (опционально)
nano instances/alexey/workspace/SOUL.md

# 6. Запустить
make deploy
```

---

## Команды

| Команда | Описание |
|---|---|
| `make add-user NAME=x BOT_TOKEN=y TG_ID=z` | Онбординг нового сотрудника |
| `make remove-user NAME=x` | Удалить инстанс |
| `make deploy` | Запустить / обновить все инстансы |
| `make restart NAME=x` | Перезапустить конкретного |
| `make logs NAME=x` | Логи инстанса |
| `make status` | Статус всех контейнеров |
| `make backup` | Бекап воркспейсов |

---

## Структура

```
instances/
  _template/     ← шаблон нового инстанса
  alexey/        ← готовый инстанс
    .env          ← секреты (не в git)
    openclaw.json ← конфиг (не в git)
    workspace/    ← SOUL.md, память, скрипты

shared/
  skills/        ← корпоративные скиллы (read-only для всех)
```

---

## Документация

- [SETUP.md](docs/SETUP.md) — установка на чистый сервер
- [PERSONAS.md](docs/PERSONAS.md) — как создать персонажа
- [ONBOARDING.md](docs/ONBOARDING.md) — онбординг нового сотрудника

---

## Изоляция данных

Каждый инстанс — отдельный Docker-контейнер с отдельным:
- воркспейсом (`instances/{name}/workspace/`)
- секретами (`instances/{name}/.env`)
- Telegram-ботом

Контейнеры не видят данные друг друга. 100% изоляция.
