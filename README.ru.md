# 🤖 corp-assistant

> **Language / Язык:** [English](README.md) | Русский

Корпоративная инфраструктура AI-ассистентов на базе [OpenClaw](https://github.com/openclaw/openclaw).

Каждый сотрудник — **изолированный персонаж**: свой Telegram-бот, своя память, свой характер. Один сервер, нулевые утечки данных между пользователями, полный контроль расходов на токены.

---

## Архитектура

```
┌──────────────────────────────────────────────────────────────────┐
│                         Docker Networks                          │
│                                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                       │
│  │  nikita  │  │  alexey  │  │  dmitry  │  ...  corp-internal   │
│  │ свой бот │  │ свой бот │  │ свой бот │                       │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘                       │
│       │             │             │                              │
│       └─────────────┼─────────────┘                              │
│                     │  ANTHROPIC_BASE_URL=http://quota-proxy     │
│            ┌────────▼────────┐                                   │
│            │  quota-proxy    │  corp-internal + corp-admin       │
│            │  :9090          │  + corp-egress (→ интернет)       │
│            │  счётчик токенов│                                   │
│            └────────┬────────┘                                   │
│                     │                                            │
│                     ▼  api.anthropic.com  (через corp-egress)    │
│                                                                  │
│  ┌──────────────────────────┐  ┌──────────────────────────────┐  │
│  │  message-broker :8080    │  │  resource-monitor :9091      │  │
│  │  inbox на инстанс        │  │  CPU/RAM/диск + алерты       │  │
│  │  auth по ключу           │  │  HTTP API /metrics /alerts   │  │
│  └──────────────────────────┘  └──────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────┐  ┌──────────────────────────────┐  │
│  │  service-agent :8090     │  │  ADMIN (Приор) 🏛️            │  │
│  │  HTTP API для бэкендов   │  │  единственный с /infra       │  │
│  │  скиллы как субпроцессы  │  │  quota / users / docker      │  │
│  └──────────────────────────┘  └──────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

### Docker-сети

| Сеть | `internal` | Кто подключён | Назначение |
|---|---|---|---|
| `corp-internal` | ✅ да | все инстансы, broker, quota-proxy, monitor | основная шина |
| `corp-admin` | ✅ да | admin, quota-proxy, monitor | управление квотами и метриками |
| `corp-egress` | ❌ нет | только quota-proxy | выход в `api.anthropic.com` |
| `corp-services` | ❌ нет | service-agent | вызовы из бэкенд-сервисов |

Флаг `internal: true` на `corp-internal` и `corp-admin` означает, что **инстансы не имеют прямого доступа в интернет** — весь LLM-трафик идёт через `quota-proxy`, который единственный подключён к не-internal сети `corp-egress`.

---

## Быстрый старт

```bash
git clone https://github.com/rekurt/corp-assistant.git /opt/corp-assistant
cd /opt/corp-assistant

# 1. Глобальные секреты (API-ключ, токены управления)
cp .env.example .env
nano .env  # ANTHROPIC_API_KEY, QUOTA_ADMIN_TOKEN, BROKER_KEY_ADMIN

# 2. Секреты admin-инстанса (обязательно — docker-compose не стартует без этого файла)
mkdir -p instances/admin
cp instances/.env.example instances/admin/.env
nano instances/admin/.env  # TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOW_FROM, BROKER_KEY

# 3. Проверка конфигурации
make security-check

# 4. Добавить первого сотрудника
make add-user NAME=alexey BOT_TOKEN=7xxx FULL_NAME="Алексей Михайлюк" TG_ID=123456789
nano instances/alexey/.env               # персональные токены (Яндекс, GitLab, …)
nano instances/alexey/workspace/SOUL.md  # настроить персонажа

# 5. Запустить
make deploy
```

---

## Команды

### Управление инстансами

| Команда | Описание |
|---|---|
| `make add-user NAME=x BOT_TOKEN=y TG_ID=z` | Онбординг нового сотрудника |
| `make remove-user NAME=x` | Удалить инстанс (с архивом воркспейса) |
| `make deploy` | Запустить / обновить все контейнеры |
| `make restart NAME=x` | Перезапустить один инстанс |
| `make logs NAME=x` | Следить за логами инстанса |
| `make status` | Статус всех контейнеров |
| `make backup` | Бэкап воркспейсов в `backups/` |

### Квоты токенов

| Команда | Описание |
|---|---|
| `make quota-report` | Отчёт за текущий месяц |
| `make quota-report MONTH=2026-03` | Отчёт за конкретный месяц |
| `make set-limit NAME=x LIMIT=500000` | Установить квоту (токенов/мес), без рестарта |
| `make quota-reset NAME=x` | Сбросить счётчик текущего месяца |

### Мониторинг

| Команда | Описание |
|---|---|
| `make monitor` | Текущие метрики CPU/RAM/диска |
| `make monitor-alerts` | Активные алерты (cooldown 1ч) |

### Service Agent

| Команда | Описание |
|---|---|
| `make service-health` | Healthcheck service-agent |
| `make service-skills` | Список доступных скиллов |
| `make add-service NAME=x PORT=y SKILLS=z` | Добавить реплику service-agent |

### Безопасность

| Команда | Описание |
|---|---|
| `make security-check` | Проверка прав `.env`, наличия ключей, gitignore |

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
- **❌ exceeded** при 100% — инстанс получает 429 и сообщает пользователю
- Лимит меняется **без рестарта**: `make set-limit NAME=alexey LIMIT=1000000`

---

## Структура репозитория

```
corp-assistant/
├── quota-proxy/          # единственное место с ANTHROPIC_API_KEY
│   ├── proxy.py          # HTTP-прокси, SQLite quota + audit log
│   └── Dockerfile
├── broker/               # шина сообщений между ассистентами
│   └── broker.py
├── resource-monitor/     # мониторинг CPU/RAM/диска, HTTP API
│   ├── monitor.py
│   └── Dockerfile
├── service-agent/        # HTTP API для бэкенд-сервисов
│   ├── server.py         # /v1/run  /v1/skills  /v1/usage
│   ├── skills/           # compliance/ и другие скиллы
│   └── Dockerfile
├── instances/
│   ├── admin/            # Приор — единственный с /infra доступом
│   ├── _template/        # шаблон нового инстанса
│   └── .env.example      # шаблон .env для инстанса
├── shared/
│   └── skills/
│       └── corp-messenger/  # скилл для обмена сообщениями
├── scripts/
│   ├── add-user.sh       # онбординг: генерирует ключи, копирует шаблон
│   ├── remove-user.sh    # удаление инстанса с архивом
│   ├── quota.sh          # CLI управления квотами
│   ├── monitor.sh        # CLI мониторинга
│   ├── add-service.sh    # добавить реплику service-agent
│   └── backup.sh         # бэкап воркспейсов
├── docs/                 # документация (см. ниже)
├── .github/
│   └── workflows/        # CI: security, release-please, GitHub Releases
└── docker-compose.yml
```

---

## CI / CD

GitHub Actions запускается при каждом пуше и PR:

| Workflow | Что делает |
|---|---|
| `security.yml` | Semgrep SAST + кастомные AI-правила, CodeQL, Trivy, Gitleaks, Hadolint, ShellCheck, pip-audit |
| `release-please.yml` | Открывает Release PR при мёрдже в `master`, обновляет `CHANGELOG.md` и `VERSION` |
| `release.yml` | При теге `v*.*.*` создаёт GitHub Release с release notes |
| `lint-commits.yml` | Проверяет Conventional Commits на заголовке PR и коммитах |

Текущая версия: [VERSION](VERSION) · [CHANGELOG](CHANGELOG.md) · [Releases](https://github.com/rekurt/corp-assistant/releases)

---

## Документация

| Документ | Описание |
|---|---|
| [docs/SETUP.md](docs/SETUP.md) | Установка на чистый сервер (Ubuntu 24.04) |
| [docs/ONBOARDING.md](docs/ONBOARDING.md) | Онбординг нового сотрудника |
| [docs/PERSONAS.md](docs/PERSONAS.md) | Создание персонажей (SOUL.md / IDENTITY.md) |
| [docs/MESSAGING.md](docs/MESSAGING.md) | Межинстансный мессенджер |
| [docs/SERVICE_AGENT.md](docs/SERVICE_AGENT.md) | HTTP API для бэкенд-сервисов |
| [docs/SECURITY.md](docs/SECURITY.md) | Threat model, исправленные уязвимости, hardening |
