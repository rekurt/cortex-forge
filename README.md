# 🤖 corp-assistant

Корпоративная инфраструктура AI-ассистентов на базе OpenClaw.

Каждый сотрудник — **изолированный персонаж**. Один сервер, нулевые утечки данных, контроль расходов.

---

## Архитектура

```
┌────────────────────────────────────────────────────────────┐
│                      Docker Network                        │
│                                                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                 │
│  │  nikita  │  │  alexey  │  │  dmitry  │  ...            │
│  │ свой бот │  │ свой бот │  │ свой бот │                 │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘                 │
│       │             │             │                        │
│       └─────────────┼─────────────┘                        │
│                     │  ANTHROPIC_BASE_URL=quota-proxy       │
│            ┌────────▼────────┐                             │
│            │  quota-proxy    │◄── считает токены           │
│            │  :9090          │    режет при лимите         │
│            └────────┬────────┘    хранит в SQLite          │
│                     │                                      │
│                     ▼ api.anthropic.com                    │
│                                                            │
│  ┌──────────────────────────────────────┐                  │
│  │  message-broker :8080                │                  │
│  │  inbox per instance, auth by key     │                  │
│  └──────────────────────────────────────┘                  │
│                                                            │
│  ┌──────────────────────────────────────┐                  │
│  │  ADMIN 🖥️  — единственный с /infra   │                  │
│  │  + make add-user / remove-user       │                  │
│  │  + quota report / reset / set-limit  │                  │
│  │  + docker control, SSH               │                  │
│  └──────────────────────────────────────┘                  │
└────────────────────────────────────────────────────────────┘
```

---

## Быстрый старт

```bash
git clone https://github.com/rekurt/corp-assistant.git /opt/corp-assistant
cd /opt/corp-assistant

cp .env.example .env
nano .env  # ANTHROPIC_API_KEY, QUOTA_ADMIN_TOKEN, BROKER_KEY_ADMIN

# Добавить первого сотрудника
make add-user NAME=alexey BOT_TOKEN=7xxx FULL_NAME="Алексей Михайлюк" TG_ID=123456789
nano instances/alexey/.env          # персональные токены
nano instances/alexey/workspace/SOUL.md  # настроить персонажа

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
| `make quota-report` | Отчёт по токенам за месяц |
| `make quota-report MONTH=2026-03` | За конкретный месяц |
| `make set-limit NAME=x LIMIT=500000` | Установить квоту (токенов/мес) |
| `make quota-reset NAME=x` | Сбросить счётчик |

---

## Квоты токенов

```
📊 Отчёт по токенам (2026-02):

  nikita       823,451 / 1,000,000 токенов  ⚠️ warning  ████████████████
               in=641,203  out=182,248  reqs=1,847

  alexey       312,008 /   500,000 токенов  ✅ ok  ██████
               in=241,500  out=70,508   reqs=892

  dmitry        45,100 /   500,000 токенов  ✅ ok  █
               in=38,200   out=6,900    reqs=203
```

- **⚠️ warning** при 80% — можно добавить alert
- **❌ exceeded** при 100% — инстанс получает 429, сообщает пользователю

---

## Структура

```
quota-proxy/          ← считает токены, хранит в SQLite
broker/               ← шина сообщений между ассистентами
instances/
  admin/              ← единственный с /infra доступом
  _template/          ← шаблон нового инстанса
  alexey/             ← готовый инстанс
shared/
  skills/
    corp-messenger/   ← скилл для общения между ассистентами
scripts/
  add-user.sh         ← онбординг + генерация quota/broker ключей
  quota.sh            ← управление квотами
```

---

## Документация

- [SETUP.md](docs/SETUP.md) — установка на чистый сервер
- [PERSONAS.md](docs/PERSONAS.md) — как создать персонажа
- [ONBOARDING.md](docs/ONBOARDING.md) — онбординг нового сотрудника
- [MESSAGING.md](docs/MESSAGING.md) — межинстансный мессенджер
