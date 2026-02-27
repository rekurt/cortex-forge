# 🤖 corp-assistant

Корпоративная инфраструктура AI-ассистентов на базе OpenClaw.

Каждый сотрудник — **изолированный персонаж**. Один сервер, нулевые утечки.

---

## Архитектура

```
┌─────────────────────────────────────────────────────┐
│                   Docker Network                    │
│                                                     │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐             │
│  │ nikita  │  │ alexey  │  │ dmitry  │  ...         │
│  │ свой бот│  │ свой бот│  │ свой бот│             │
│  └────┬────┘  └────┬────┘  └────┬────┘             │
│       │            │            │                   │
│       └────────────┼────────────┘                   │
│                    │                                │
│           ┌────────▼────────┐                       │
│           │ message-broker  │  ← только внутри сети │
│           │  (HTTP :8080)   │                       │
│           └─────────────────┘                       │
│                                                     │
│  ┌──────────────────────────────────────┐           │
│  │  ADMIN (🖥️ Сервер)                   │           │
│  │  + монтирует /infra (всё дерево)     │           │
│  │  + make add-user / remove-user       │           │
│  │  + docker status / logs / deploy     │           │
│  │  + SSH на сервер                     │           │
│  └──────────────────────────────────────┘           │
└─────────────────────────────────────────────────────┘
```

**Изоляция:**
- Персональные инстансы видят только свой воркспейс
- Брокер: каждый читает только свой inbox, подделать sender нельзя
- Admin — единственный с доступом к `/infra` и серверу

---

## Быстрый старт

```bash
# 1. Клонировать на сервер
git clone https://github.com/rekurt/corp-assistant.git /opt/corp-assistant
cd /opt/corp-assistant

# 2. Настроить глобальный конфиг
cp .env.example .env
nano .env  # ANTHROPIC_API_KEY + BROKER_KEY_ADMIN

# 3. Настроить admin-инстанс
nano instances/admin/.env    # BOT_TOKEN, TG_ID владельца
cp instances/_template/openclaw.json.template instances/admin/openclaw.json
nano instances/admin/openclaw.json

# 4. Добавить сотрудника
make add-user NAME=alexey BOT_TOKEN=7xxx FULL_NAME="Алексей Михайлюк" TG_ID=123456789

# 5. Запустить
make deploy
```

---

## Команды

| Команда | Описание |
|---|---|
| `make add-user NAME=x BOT_TOKEN=y TG_ID=z` | Онбординг нового сотрудника |
| `make remove-user NAME=x` | Удалить инстанс (с архивом) |
| `make deploy` | Запустить / обновить все |
| `make restart NAME=x` | Перезапустить одного |
| `make logs NAME=x` | Логи инстанса |
| `make status` | Статус всех контейнеров |
| `make backup` | Бекап воркспейсов |

---

## Структура

```
instances/
  admin/           ← единственный с доступом к инфре
  _template/       ← шаблон нового инстанса
  alexey/          ← готовый инстанс
    .env            ← секреты (не в git)
    openclaw.json   ← конфиг (не в git)
    workspace/      ← SOUL.md, память, скрипты

shared/
  skills/
    corp-messenger/ ← скилл для общения между ассистентами

broker/
  broker.py        ← HTTP-брокер сообщений
  Dockerfile
```

---

## Документация

- [SETUP.md](docs/SETUP.md) — установка на чистый сервер
- [PERSONAS.md](docs/PERSONAS.md) — как создать персонажа
- [ONBOARDING.md](docs/ONBOARDING.md) — онбординг нового сотрудника
- [MESSAGING.md](docs/MESSAGING.md) — как работает межинстансный мессенджер
