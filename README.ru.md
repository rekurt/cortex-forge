# 🐒 CortexForge

<p align="center">
  <img src="assets/banner.jpg" alt="CortexForge — изолированные AI-персонажи для каждого сотрудника" width="1200"/>
</p>

> **Language / Язык:** [English](README.md) | Русский

[![Version](https://img.shields.io/github/v/tag/user-1/cortex-forge?label=версия&color=blue)](https://github.com/example-org/cortex-forge/releases)
[![CI Security](https://github.com/example-org/cortex-forge/actions/workflows/security.yml/badge.svg)](https://github.com/example-org/cortex-forge/actions/workflows/security.yml)
[![License: MIT](https://img.shields.io/badge/лицензия-MIT-green)](LICENSE)

Корпоративная инфраструктура AI-ассистентов на базе [OpenClaw](https://github.com/openclaw/openclaw).

Каждый сотрудник — **изолированный персонаж**: свой Telegram-бот, своя память, свой характер.  
Один сервер. Нулевые утечки данных между пользователями. Полный контроль расходов на токены.

---

## Линейка продуктов

CortexForge поставляется как набор сфокусированных компонентов — разворачивайте все или только нужные:

| Компонент | Описание |
|---|---|
| 🧠 **CortexForge Core** | Основной рантайм — изолированные AI-персонажи, по одному на сотрудника |
| 🔐 **CortexForge Proxy** | Квотирование токенов — единственный контейнер, который хранит реальный API-ключ |
| 🏛️ **CortexForge Admin** | Admin-инстанс — управление инфраструктурой, квотами и Docker |
| 📨 **CortexForge Broker** | Шина сообщений — позволяет ассистентам отправлять сообщения друг другу |

---

## Зачем CortexForge?

Большинство команд используют единый AI-инструмент — один контекст на всех, никаких личных настроек, и непонятно кто сколько тратит. CortexForge решает это:

| Проблема | Решение |
|---|---|
| Общий API-ключ, нет учёта расходов | Квоты токенов на инстанс в SQLite, отчёт в реальном времени |
| Все сотрудники в одном контексте | Полная изоляция — у каждого своя память и персонаж |
| Один ассистент на всех | Каждый сотрудник настраивает персонажа под себя (имя, стиль, скиллы) |
| Утечка API-ключа через промпты | Ключ только в `quota-proxy`; инстансы его не видят никогда |
| Нет audit trail | Полный лог каждого API-вызова, изменения квоты, действия админа |
| Сложный онбординг/оффбординг | `make add-user` / `make remove-user` — одна команда |

---

## Возможности

- 🔒 **Ключ не утекает** — `ANTHROPIC_API_KEY` живёт только в `quota-proxy`; инстансы получают `QUOTA_KEY` без доступа к API
- 📊 **Квоты токенов** — месячные лимиты на инстанс с предупреждением (80%) и жёстким порогом (100%); меняются без рестарта
- 🧑‍🤝‍🧑 **Изолированные персонажи** — у каждого сотрудника свой бот, воркспейс, память и характер (`SOUL.md`)
- 💬 **Межинстансные сообщения** — ассистенты могут отправлять сообщения друг другу через `message-broker`
- 🏛️ **Инстанс-администратор (Admin)** — выделенный admin-бот с полным доступом к инфраструктуре, управлением квотами и Docker
- 📈 **Resource Monitor** — метрики CPU/RAM/диска с настраиваемыми порогами алертов
- 🔌 **Service Agent** — HTTP API для бэкенд-сервисов, запускает скиллы как субпроцессы (например, compliance-проверки)
- 🛡️ **Security pipeline** — Semgrep, CodeQL, Trivy, Gitleaks, Hadolint, ShellCheck при каждом коммите
- 🔄 **Release automation** — release-please автогенерирует changelog и GitHub Releases при мёрдже в `master`
- 🐳 **Только Docker Compose** — без Kubernetes и Helm; работает на одном Ubuntu VPS

---

## Архитектура

```
┌──────────────────────────────────────────────────────────────────┐
│                         Docker Networks                          │
│                                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                       │
│  │  user-1  │  │  user-2  │  │  user-3  │  ...  corp-internal   │
│  │ свой бот │  │ свой бот │  │ свой бот │                       │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘                       │
│       │             │             │                              │
│       └─────────────┼─────────────┘                              │
│                     │  ANTHROPIC_BASE_URL=http://quota-proxy     │
│            ┌────────▼─────────┐                                  │
│            │   quota-proxy    │  corp-internal                   │
│            │   :9090          │  corp-admin                      │
│            │                  │  corp-egress ──► интернет        │
│            │  ✓ считает токены│                                  │
│            │  ✓ режет лимиты  │                                  │
│            │  ✓ audit log     │                                  │
│            └────────┬─────────┘                                  │
│                     │                                            │
│                     ▼  api.anthropic.com                         │
│                                                                  │
│  ┌───────────────────────┐   ┌──────────────────────────────┐   │
│  │  message-broker :8080 │   │  resource-monitor :9091      │   │
│  │  inbox на инстанс     │   │  CPU / RAM / диск            │   │
│  │  auth по ключу        │   │  алерты + HTTP API           │   │
│  └───────────────────────┘   └──────────────────────────────┘   │
│                                                                  │
│  ┌───────────────────────┐   ┌──────────────────────────────┐   │
│  │  service-agent :8090  │   │  ADMIN — Admin 🏛️            │   │
│  │  /v1/run  /v1/skills  │   │  /infra доступ               │   │
│  │  скиллы как subprocess│   │  quota / users / docker      │   │
│  └───────────────────────┘   └──────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

### Как проходит запрос

1. Сотрудник отправляет сообщение своему Telegram-боту
2. OpenClaw внутри контейнера обращается к Anthropic API — но `ANTHROPIC_BASE_URL` указывает на `quota-proxy`, а не на Anthropic напрямую
3. `quota-proxy` проверяет квоту токенов, обновляет счётчик в SQLite, затем форвардит запрос в `api.anthropic.com` через сеть `corp-egress`
4. Если квота исчерпана — `quota-proxy` немедленно возвращает HTTP 429, реальный вызов не делается

### Docker-сети

| Сеть | `internal` | Кто подключён | Назначение |
|---|---|---|---|
| `corp-internal` | ✅ да | все инстансы, broker, quota-proxy, monitor | основная шина — нет прямого интернета |
| `corp-admin` | ✅ да | admin, quota-proxy, monitor | управление квотами и метриками — нет интернета |
| `corp-egress` | ❌ нет | **только** quota-proxy | единственный путь до `api.anthropic.com` |
| `corp-services` | ❌ нет | service-agent | вызовы из бэкенд-сервисов |

Инстансы подключены только к `corp-internal` — они не могут выйти в интернет напрямую, не видят `corp-admin` и не имеют доступа к `service-agent`. `quota-proxy` — единственный мост между внутренними сетями и интернетом.

---

## Требования

| Компонент | Минимум | Рекомендуется |
|---|---|---|
| ОС | Ubuntu 22.04 LTS | Ubuntu 24.04 LTS |
| CPU | 2 ядра | 4+ ядра |
| RAM | 4 GB | 8+ GB (~500 MB на инстанс) |
| Диск | 20 GB | 50+ GB |
| Docker | 24+ | latest |
| Docker Compose | 2.x | latest |

---

## Быстрый старт

### 1. Клонировать и настроить глобальные секреты

```bash
git clone https://github.com/example-org/cortex-forge.git /opt/CortexForge
cd /opt/CortexForge

cp .env.example .env
chmod 600 .env
nano .env
```

Минимально необходимые поля:

```bash
ANTHROPIC_API_KEY=sk-ant-...          # ваш ключ Anthropic
QUOTA_ADMIN_TOKEN=<random-32-chars>   # токен управления квотами
BROKER_KEY_ADMIN=<random-32-chars>    # ключ admin в брокере
MONITOR_ADMIN_TOKEN=<random-32-chars> # токен resource-monitor API
SERVICE_API_KEY=<random-32-chars>     # Bearer-токен service-agent
```

Сгенерировать случайный токен:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 2. Создать admin-инстанс (Admin)

Admin-инстанс **обязателен** — `docker-compose.yml` ссылается на `instances/admin/.env` при старте. Без этого файла `docker compose config` упадёт с ошибкой.

```bash
mkdir -p instances/admin
cp instances/.env.example instances/admin/.env
chmod 600 instances/admin/.env
nano instances/admin/.env
```

Обязательные поля:

```bash
TELEGRAM_BOT_TOKEN=7000000000:AAxxxx  # токен бота Adminа (от @BotFather)
TELEGRAM_ALLOW_FROM=123456789         # ваш Telegram ID (от @userinfobot)
BROKER_KEY=<то же что BROKER_KEY_ADMIN> # должно совпадать с глобальным .env
```

### 3. Проверить конфигурацию

```bash
make security-check
```

Все пункты должны показывать ✅. Исправь ❌ до деплоя.

### 4. Добавить первого сотрудника

```bash
make add-user NAME=user-2 \
              BOT_TOKEN=7000000000:AAxxxx \
              FULL_NAME="Example User" \
              TG_ID=123456789
```

Скрипт автоматически:
- Создаёт `instances/user-2/` из шаблона
- Генерирует уникальные `BROKER_KEY` и `QUOTA_KEY`
- Добавляет ключи и лимит 1M токенов/мес в `.env`
- Выводит YAML-блок для вставки в `docker-compose.yml`

Опционально — заполнить личные токены и настроить персонажа:
```bash
nano instances/user-2/.env               # Яндекс OAuth, GitLab token, etc.
nano instances/user-2/workspace/SOUL.md  # стиль и характер ассистента
```

### 5. Запустить

```bash
make deploy
make status    # все контейнеры должны быть Up (healthy)
```

---

## Справочник конфигурации

### Глобальный `.env`

| Переменная | Обязательно | Описание |
|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ | API-ключ Anthropic — читает только `quota-proxy` |
| `QUOTA_ADMIN_TOKEN` | ✅ | Bearer-токен для API управления квотами |
| `QUOTA_DEFAULT_MONTHLY` | — | Лимит токенов по умолчанию (по умолчанию: `1000000`) |
| `BROKER_KEY_ADMIN` | ✅ | Ключ admin в брокере |
| `MONITOR_ADMIN_TOKEN` | ✅ | Bearer-токен для API resource-monitor |
| `SERVICE_API_KEY` | ✅ | Bearer-токен для service-agent |
| `ENRICH_PY_PATH` | — | Путь к `enrich.py` на хосте для compliance-скилла |
| `DADATA_API_KEY` | — | API-ключ DaData (для compliance-проверок) |
| `ALERT_CPU_PCT` | — | Порог алерта CPU в % (по умолчанию: `80`) |
| `ALERT_RAM_PCT` | — | Порог алерта RAM в % (по умолчанию: `85`) |
| `ALERT_DISK_PCT` | — | Порог алерта диска в % (по умолчанию: `90`) |

### `.env` инстанса (`instances/<name>/.env`)

| Переменная | Обязательно | Описание |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | ✅ | Токен Telegram-бота (от @BotFather) |
| `TELEGRAM_ALLOW_FROM` | ✅ | Разрешённые Telegram ID через запятую |
| `BROKER_KEY` | ✅ | Ключ брокера (генерируется `add-user.sh`) |
| `YANDEX_OAUTH_TOKEN` | — | Яндекс OAuth для почты / Трекера |
| `YANDEX_CALDAV_URL` | — | CalDAV URL Яндекс Календаря |
| `YANDEX_USER` | — | Логин Яндекс |
| `YANDEX_APP_PASSWORD` | — | Пароль приложения Яндекс |
| `GITLAB_TOKEN` | — | GitLab Personal Access Token |

---

## Команды

### Управление инстансами

| Команда | Описание |
|---|---|
| `make add-user NAME=x BOT_TOKEN=y TG_ID=z` | Онбординг нового сотрудника |
| `make remove-user NAME=x` | Удалить инстанс (сначала архивирует воркспейс в `backups/`) |
| `make deploy` | Запустить / пересобрать все контейнеры |
| `make restart NAME=x` | Перезапустить один инстанс |
| `make logs NAME=x` | Логи инстанса в реальном времени |
| `make status` | Статус всех контейнеров |
| `make backup` | Бэкап всех воркспейсов в `backups/` |

### Квоты токенов

| Команда | Описание |
|---|---|
| `make quota-report` | Отчёт за текущий месяц |
| `make quota-report MONTH=2026-03` | Отчёт за конкретный месяц |
| `make set-limit NAME=x LIMIT=500000` | Установить квоту (токенов/мес), **без рестарта** |
| `make quota-reset NAME=x` | Сбросить счётчик текущего месяца |

### Мониторинг

| Команда | Описание |
|---|---|
| `make monitor` | Текущие метрики CPU / RAM / диска |
| `make monitor-alerts` | Активные алерты (cooldown 1ч на тип) |

### Service Agent

| Команда | Описание |
|---|---|
| `make service-health` | Healthcheck service-agent |
| `make service-skills` | Список доступных скиллов с параметрами |
| `make add-service NAME=x PORT=y SKILLS=z` | Добавить реплику service-agent |

### Безопасность

| Команда | Описание |
|---|---|
| `make security-check` | Проверка прав `.env`, наличия ключей, gitignore |

---

## Квоты токенов

Квоты применяются в `quota-proxy` до того, как запрос достигает Anthropic — даже если модель запрашивает больше токенов, прокси блокирует это.

```
📊 Отчёт по токенам (2026-02):

  user-1       823,451 / 1,000,000 токенов  ⚠️ warning  ████████████████
               in=641,203  out=182,248  reqs=1,847

  user-2       312,008 /   500,000 токенов  ✅ ok  ██████
               in=241,500  out=70,508   reqs=892

  user-3        45,100 /   500,000 токенов  ✅ ok  █
               in=38,200   out=6,900    reqs=203
```

- **✅ ok** — меньше 80%
- **⚠️ warning** — 80–99% — уведомляет администратора
- **❌ exceeded** — 100% — quota-proxy возвращает HTTP 429; инстанс сообщает пользователю
- Квота сбрасывается 1-го числа каждого месяца (или вручную через `make quota-reset`)
- Лимит меняется **без рестарта**: `make set-limit NAME=user-2 LIMIT=1000000`

---

## Персонажи

Поведение каждого инстанса определяется двумя файлами в `instances/<name>/workspace/`:

**`SOUL.md`** — как ассистент думает и общается:
```markdown
Ты — точный, системный, без лирики.
Дай факты, цифры, структуру. Никаких "наверное".
Если данных нет — говори прямо.
```

**`IDENTITY.md`** — имя, роль, emoji:
```markdown
- Name: Вектор
- Emoji: 📐
- Vibe: точный, сухой, надёжный
```

**`USER.md`** — контекст о сотруднике (роль, часовой пояс, предпочтения):
```markdown
- Name: Пользователь 2
- Role: Backend Lead
- Timezone: UTC+3
```

Admin-инстанс называется **Admin** 🏛️ (настоятель монастыря капуцинов — он управляет всеми инстансами). Admin — единственный инстанс с доступом к `/infra`, управлением Docker и квотами.

---

## Структура репозитория

```
CortexForge/
├── quota-proxy/          # единственное место с ANTHROPIC_API_KEY
│   ├── proxy.py          # HTTP-прокси + SQLite quota & audit log
│   └── Dockerfile
├── broker/               # шина сообщений между ассистентами
│   └── broker.py         # in-memory inbox на инстанс, auth по ключу
├── resource-monitor/     # мониторинг CPU/RAM/диска
│   ├── monitor.py        # сбор метрик, cooldown алертов, HTTP API
│   └── Dockerfile
├── service-agent/        # HTTP API для бэкенд-сервисов
│   ├── server.py         # /v1/run  /v1/skills  /v1/health  /v1/usage
│   ├── skills/
│   │   └── compliance/   # проверка контрагента (вызывает enrich.py)
│   └── Dockerfile
├── instances/
│   ├── admin/            # Admin — единственный с /infra доступом
│   │   └── workspace/    # IDENTITY.md, SOUL.md, AGENTS.md
│   ├── _template/        # копируется add-user.sh при каждом онбординге
│   └── .env.example      # шаблон .env для инстанса
├── shared/
│   └── skills/
│       └── corp-messenger/  # скилл для отправки/чтения сообщений брокера
├── scripts/
│   ├── add-user.sh       # онбординг: ключи, копирование шаблона, docker-compose
│   ├── remove-user.sh    # удаление инстанса с архивом воркспейса
│   ├── quota.sh          # CLI квот (report / reset / set-limit)
│   ├── monitor.sh        # CLI мониторинга
│   ├── add-service.sh    # добавить реплику service-agent
│   └── backup.sh         # бэкап воркспейсов (tar.gz на инстанс)
├── docs/
│   ├── SETUP.md          # руководство по установке на сервер
│   ├── ONBOARDING.md     # руководство по онбордингу сотрудника
│   ├── PERSONAS.md       # руководство по созданию персонажей
│   ├── MESSAGING.md      # справочник API межинстансного мессенджера
│   ├── SERVICE_AGENT.md  # справочник API service-agent
│   └── SECURITY.md       # threat model, таблица CVE, hardening
├── .github/
│   ├── workflows/
│   │   ├── security.yml        # Semgrep, CodeQL, Trivy, Gitleaks, Hadolint
│   │   ├── release-please.yml  # автоматические Release PR
│   │   ├── release.yml         # GitHub Releases при пуше тега
│   │   └── lint-commits.yml    # Conventional Commits
│   ├── semgrep/
│   │   └── ai-security.yml     # 10 кастомных AI-правил безопасности
│   └── scripts/
│       └── ai_security_check.py  # 8 проектных проверок безопасности
├── CHANGELOG.md
├── VERSION
└── docker-compose.yml
```

---

## CI / CD

GitHub Actions запускается при каждом пуше и PR:

| Workflow | Jobs | Что проверяет |
|---|---|---|
| `security.yml` | secrets-scan, sast-python, ai-security, codeql, docker-lint, shellcheck, deps-audit, trivy-images | Полная поверхность безопасности |
| `release-please.yml` | release-please | Открывает Release PR, обновляет `CHANGELOG.md` + `VERSION` |
| `release.yml` | github-release | Создаёт GitHub Release с release notes при теге `v*.*.*` |
| `lint-commits.yml` | pr-title, commits, release-ready | Conventional Commits на PR и коммитах |

**Кастомные AI-правила** (`ai_security_check.py`) проверяют 8 проектных паттернов:
- Чтение inbox брокера без проверки авторизации
- Порядок проверки квоты (должна быть до upstream-запроса)
- Auth MCP-сервера + timing attack на сравнение токена
- Инъекция имени скилла в service-agent (subprocess до проверки `ALLOWED_SKILLS`)
- Захардкоженные токены (6 паттернов: Anthropic, GitLab, GitHub, Slack, AWS, Telegram)
- Docker network exposure для чувствительных сервисов
- Path traversal в `add-user.sh`
- Реальные секреты в `.env.example`

Текущая версия: [VERSION](VERSION) · [CHANGELOG](CHANGELOG.md) · [Releases](https://github.com/example-org/cortex-forge/releases)

---

## Безопасность — ключевые моменты

- **Изоляция API-ключа** — `ANTHROPIC_API_KEY` никогда не монтируется в инстансы; они получают только `QUOTA_KEY` в рамках своей квоты
- **Сегментация сетей** — 4 Docker-сети; инстансы на `corp-internal` (internal: true) не могут выйти в интернет напрямую
- **Constant-time сравнение токенов** — все Bearer token checks через `hmac.compare_digest`
- **Rate limiting** — leaky bucket по IP на admin-эндпоинтах; лимиты размера сообщений в брокере
- **Resource limits** — лимиты CPU и RAM на каждый контейнер через `deploy.resources`
- **Non-root контейнеры** — все контейнеры работают от непривилегированного пользователя `app` с `no-new-privileges:true`
- **Read-only монтирование** — директории скиллов и `enrich.py` монтируются `:ro`
- **Audit log** — каждый API-вызов, изменение квоты и действие администратора логируется в SQLite

Подробности: [docs/SECURITY.md](docs/SECURITY.md)

---

## Диагностика

### `docker compose config` падает с "env file not found"

Отсутствует `instances/admin/.env`. Создай:
```bash
mkdir -p instances/admin
cp instances/.env.example instances/admin/.env
nano instances/admin/.env
```

### Контейнер инстанса постоянно перезапускается

```bash
make logs NAME=user-2
```

Частые причины:
- Неверный `TELEGRAM_BOT_TOKEN` — проверь: `curl https://api.telegram.org/bot<token>/getMe`
- Отсутствует обязательное поле в `.env`

### quota-proxy не может достучаться до api.anthropic.com

Проверь что `quota-proxy` подключён к сети `corp-egress`:
```bash
docker inspect corp-quota | grep -A5 Networks
```

Должна быть `corp-egress`. Если нет — выполни `make deploy` для пересоздания с актуальным `docker-compose.yml`.

### Квота исчерпана неожиданно

```bash
make quota-report
```

Увеличить лимит без рестарта:
```bash
make set-limit NAME=user-2 LIMIT=2000000
```

### service-agent возвращает "Skill not in allowed list"

Вайтлист скиллов (`_ALLOWED_SKILLS`) заполняется при старте из `SKILLS_DIR`. Перезапусти контейнер после добавления нового скилла:
```bash
docker compose restart assistant-service
```

---

## Документация

| Документ | Описание |
|---|---|
| [docs/SETUP.md](docs/SETUP.md) | Установка на сервер (Ubuntu 24.04), systemd, cron-бэкап |
| [docs/ONBOARDING.md](docs/ONBOARDING.md) | Полный чеклист онбординга сотрудника |
| [docs/PERSONAS.md](docs/PERSONAS.md) | Создание персонажей с примерами (SOUL.md / IDENTITY.md) |
| [docs/MESSAGING.md](docs/MESSAGING.md) | Справочник API межинстансного мессенджера |
| [docs/SERVICE_AGENT.md](docs/SERVICE_AGENT.md) | HTTP API service-agent, добавление скиллов, репликация |
| [docs/SECURITY.md](docs/SECURITY.md) | Threat model, 17 закрытых уязвимостей, CI/CD pipeline, roadmap |

---

## Участие в разработке

1. Сделай форк и создай ветку: `git checkout -b feat/your-feature`
2. Следуй [Conventional Commits](https://www.conventionalcommits.org): `feat:`, `fix:`, `docs:`, `ci:`, `security:`
3. Запусти `make security-check` и `python3 .github/scripts/ai_security_check.py` локально перед пушем
4. Открой PR в `master` — CI автоматически запустит все проверки безопасности

---

## Лицензия

MIT — см. [LICENSE](LICENSE)
