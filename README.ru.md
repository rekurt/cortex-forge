# 🐒 CortexForge — игрушечный проект, небезопасен для production

<p align="center">
  <img src="assets/banner.jpg" alt="CortexForge — изолированные AI-персонажи для каждого сотрудника" width="1200"/>
</p>

> **Экспериментальный проект для развлечения. Не использовать в production.**
> CortexForge — это Docker Compose playground для экспериментов с изолированными AI-инстансами, квотами, мессенджером и персонажами. Проект **не проходил аудит**, **не рассчитан на реальные данные сотрудников** и содержит намеренно мощные admin-возможности: доступ к Docker socket, rw-монтирование всего проекта и OAuth-proxy эксперименты. Это лаборатория, а не enterprise security product.
>
> **Language / Язык:** [English](README.md) | Русский

[![Version](https://img.shields.io/github/v/tag/example-org/cortex-forge?label=версия&color=blue)](https://github.com/example-org/cortex-forge/releases)
[![CI Security](https://github.com/example-org/cortex-forge/actions/workflows/security.yml/badge.svg)](https://github.com/example-org/cortex-forge/actions/workflows/security.yml)
[![License: MIT](https://img.shields.io/badge/лицензия-MIT-green)](LICENSE)

CortexForge — экспериментальная песочница AI-ассистентов на базе [OpenClaw](https://github.com/openclaw/openclaw).

Идея простая: поднять на одном хосте несколько изолированных Telegram-ботов, у каждого — свой workspace, персонаж, квота токенов и inbox.

---

## Что это за проект

Проект полезен для:

- экспериментов с персональными AI-инстансами в контейнерах
- проверки квотирования перед model API
- простого мессенджера между ассистентами
- прототипирования persona/workspace-based поведения
- локального запуска automation skills через HTTP API

Проект **не подходит** для:

- production-ассистентов сотрудников
- регулируемых данных, секретов, клиентских данных и конфиденциальных документов
- multi-tenant сценариев с реальными trust boundaries
- окружений, где недопустимы Docker socket, широкие bind mounts или OAuth-proxy эксперименты

---

## Компоненты

CortexForge состоит из нескольких небольших сервисов:

| Компонент | Описание |
|---|---|
| **OpenClaw-инстансы** | Один admin-инстанс и опциональные сгенерированные user-инстансы |
| **CLIProxyAPI** | Опциональный OAuth-прокси для Codex/Claude Max-like доступа; хранит OAuth-сессию в Docker volume |
| **quota-proxy** | Квоты, rate-limit и аудит перед upstream model endpoint |
| **message-broker** | SQLite-backed inbox/шина сообщений между инстансами |
| **resource-monitor** | Метрики контейнеров и quota alerts |
| **service-agent** | Локальный HTTP API, который запускает разрешённые skills как subprocess |

---

## Зачем он существует

Проект вырос из идеи посмотреть, как может выглядеть “офис маленьких персональных AI-ботов”. Фокус — операционные механики, а не production security:

| Эксперимент | Реализация |
|---|---|
| Контекст на инстанс | Отдельные workspace, memory, Telegram token и persona files |
| Квотирование | `quota-proxy` хранит месячные счётчики в SQLite |
| Admin control plane | Admin OpenClaw-инстанс монтирует repo как `/infra` и видит Docker |
| Сообщения между ботами | `message-broker` даёт `/send`, `/inbox` и admin inbox views |
| Skill execution | `service-agent` читает manifests и запускает allowlisted subprocesses |

---

## Возможности

- 🔒 **Паттерн quota key** — user-инстансы получают `QUOTA_KEY_*` и ходят в локальный `quota-proxy`
- 📊 **Квоты токенов** — месячные лимиты на инстанс с предупреждением (80%) и жёстким порогом (100%); меняются без рестарта
- 🧑‍🤝‍🧑 **Изолированные персонажи** — у каждого сгенерированного инстанса свой бот, воркспейс, память и характер (`SOUL.md`)
- 💬 **Межинстансные сообщения** — ассистенты могут отправлять сообщения друг другу через `message-broker`
- 🏛️ **Admin-инстанс** — намеренно мощный admin-бот с доступом к `/infra` и Docker
- 📈 **Resource Monitor** — метрики CPU/RAM/диска с настраиваемыми порогами алертов
- 🔌 **Service Agent** — HTTP API для бэкенд-сервисов, запускает скиллы как субпроцессы (например, compliance-проверки)
- 🛡️ **Security checks** — Gitleaks, Semgrep, Bandit, Trivy, Hadolint, ShellCheck и кастомные AI checks в CI
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
│                     │  openclaw.json baseUrl=http://quota-proxy  │
│            ┌────────▼─────────┐                                  │
│            │   quota-proxy    │  corp-internal                   │
│            │   :9090          │  corp-admin                      │
│            │                  │  corp-egress ──► интернет        │
│            │  ✓ считает токены│                                  │
│            │  ✓ режет лимиты  │                                  │
│            │  ✓ audit log     │                                  │
│            └────────┬─────────┘                                  │
│                     │                                            │
│                     ▼  CLIProxyAPI или api.anthropic.com         │
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
2. OpenClaw внутри контейнера обращается к провайдеру из `openclaw.json`; user template указывает `baseUrl` на `http://quota-proxy:9090`
3. `quota-proxy` проверяет квоту токенов, обновляет счётчик в SQLite, затем по умолчанию форвардит запрос в CLIProxyAPI (`http://cliproxyapi:8317`) или в direct upstream, если он настроен отдельно
4. Если квота исчерпана — `quota-proxy` немедленно возвращает HTTP 429, реальный вызов не делается

### Docker-сети

| Сеть | `internal` | Кто подключён | Назначение |
|---|---|---|---|
| `corp-internal` | ✅ да | admin, сгенерированные инстансы, broker, quota-proxy, monitor, service-agent | внутренняя шина — нет прямого интернета |
| `corp-admin` | ✅ да | admin, quota-proxy, monitor | управление квотами и метриками — нет интернета |
| `corp-egress` | ❌ нет | quota-proxy, CLIProxyAPI | egress к upstream model/OAuth |
| `corp-services` | ❌ нет | service-agent | вызовы из бэкенд-сервисов |
| `corp-outbound` | ❌ нет | admin и сгенерированные инстансы | Telegram и другие внешние non-model API |

Сгенерированные user-инстансы не подключаются к `corp-admin` и не монтируют `/infra`. Но у них есть `corp-outbound` для Telegram и других внешних вызовов, поэтому это **не** air-gapped и не production-grade isolation model.

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
| Python | 3.12+ | 3.12+ |
| ShellCheck | опционально локально | нужен для полного локального lint |

---

## Быстрый старт

### 1. Клонировать и настроить локальные секреты

```bash
git clone https://github.com/example-org/cortex-forge.git /opt/CortexForge
cd /opt/CortexForge

cp .env.example .env
chmod 600 .env
nano .env
```

Минимально необходимые локальные значения:

```bash
ANTHROPIC_API_KEY=sk-ant-...          # используется admin-инстансом напрямую
CLIPROXY_API_KEY=clip-...             # auth quota-proxy -> CLIProxyAPI
QUOTA_ADMIN_TOKEN=<random-32-chars>   # токен admin API quota-proxy
BROKER_KEY_ADMIN=<random-32-chars>    # ключ admin в брокере
BROKER_KEY_SERVICE=<random-32-chars>  # ключ service-agent в брокере
BROKER_KEY_MONITOR=<random-32-chars>  # ключ monitor в брокере
MONITOR_ADMIN_TOKEN=<random-32-chars> # токен resource-monitor API
SERVICE_API_KEY=svc-...               # Bearer-токен service-agent
```

Сгенерировать случайный токен:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
python3 -c "import secrets; print('clip-' + secrets.token_urlsafe(24))"
python3 -c "import secrets; print('svc-' + secrets.token_urlsafe(24))"
```

### 2. Поднять OAuth для CLIProxyAPI или сменить upstream mode

`docker-compose.yml` сейчас направляет `quota-proxy` в CLIProxyAPI:

```yaml
UPSTREAM_URL=http://cliproxyapi:8317
UPSTREAM_API_KEY=${CLIPROXY_API_KEY}
```

Значит, до реальных model calls для user-инстансов CLIProxyAPI должен иметь OAuth credential в Docker volume `cliproxyapi-auths`. Headless-процедура логина описана в [CLAUDE.md](CLAUDE.md). Без OAuth state контейнер CLIProxyAPI может рестартовать без явной ошибки, но реальные вызовы модели через него работать не будут.

Для более простого локального эксперимента можно заменить `UPSTREAM_URL` на direct provider endpoint и передать совместимый upstream key. Реальные credentials не коммитить.

### 3. Создать admin-инстанс (Admin)

Admin-инстанс **обязателен** — `docker-compose.yml` ссылается на `instances/admin/.env` при старте. Без этого файла `docker compose config` упадёт с ошибкой.

```bash
mkdir -p instances/admin
cp instances/.env.example instances/admin/.env
chmod 600 instances/admin/.env
nano instances/admin/.env
```

Обязательные поля:

```bash
TELEGRAM_BOT_TOKEN=0000000000:CHANGE_ME_BOT_TOKEN
TELEGRAM_ALLOW_FROM=000000000         # Telegram user ID
BROKER_KEY=<то же что BROKER_KEY_ADMIN> # должно совпадать с глобальным .env
```

### 4. Проверить конфигурацию

```bash
make security-check
```

Все пункты должны показывать ✅. Исправь ❌ до деплоя.

### 5. Добавить первый сгенерированный инстанс

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
- Добавляет сервис в `docker-compose.override.yml` (gitignored)

Опционально — заполнить личные токены и настроить персонажа:
```bash
nano instances/user-2/.env               # Яндекс OAuth, GitLab token, etc.
nano instances/user-2/workspace/SOUL.md  # стиль и характер ассистента
```

### 6. Запустить

```bash
make deploy
make status    # все контейнеры должны быть Up (healthy)
```

---

## Справочник конфигурации

### Глобальный `.env`

| Переменная | Обязательно | Описание |
|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ | API-ключ Anthropic для прямого доступа admin-инстанса; сгенерированные инстансы должны ходить через quota keys и `quota-proxy` |
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
| `TELEGRAM_BOT_TOKEN` | ✅ | Placeholder токена Telegram-бота |
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

Квоты применяются в `quota-proxy` до того, как сгенерированный инстанс достигает настроенного upstream (по умолчанию CLIProxyAPI, либо direct API при ручной перенастройке).

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
├── cliproxyapi/          # конфиг и entrypoint CLIProxyAPI для OAuth proxy mode
├── quota-proxy/          # quota/rate-limit/audit proxy для сгенерированных инстансов
│   ├── proxy.py          # HTTP-прокси + SQLite quota & audit log
│   └── Dockerfile
├── broker/               # шина сообщений между ассистентами
│   └── broker.py         # SQLite-persistent inbox на инстанс, auth по ключу
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
│   │   ├── security.yml        # Gitleaks, Semgrep, Bandit, Trivy, Hadolint, ShellCheck
│   │   ├── release-please.yml  # автоматические Release PR
│   │   ├── release.yml         # GitHub Releases при пуше тега
│   │   └── lint-commits.yml    # Conventional Commits
│   ├── semgrep/
│   │   └── ai-security.yml     # 14 кастомных AI/security правил
│   └── scripts/
│       └── ai_security_check.py  # 9 проектных проверок безопасности
├── CHANGELOG.md
├── VERSION
└── docker-compose.yml
```

---

## CI / CD

GitHub Actions запускается при каждом пуше и PR:

| Workflow | Jobs | Что проверяет |
|---|---|---|
| `security.yml` | secrets-scan, sast-python, ai-security, docker-lint, shellcheck, deps-audit, trivy-images | Secret scanning, Python SAST, кастомные AI checks, container lint/scans |
| `release-please.yml` | release-please | Открывает Release PR, обновляет `CHANGELOG.md` + `VERSION` |
| `release.yml` | github-release | Создаёт GitHub Release с release notes при теге `v*.*.*` |
| `lint-commits.yml` | pr-title, commits, release-ready | Conventional Commits на PR и коммитах |

**Кастомные Python-проверки** (`ai_security_check.py`) покрывают 9 проектных паттернов:
- Чтение inbox брокера без проверки авторизации
- Порядок проверки квоты (должна быть до upstream-запроса)
- Auth MCP-сервера + timing attack на сравнение токена
- Инъекция имени скилла в service-agent (subprocess до проверки `ALLOWED_SKILLS`)
- Захардкоженные токены (6 паттернов: Anthropic, GitLab, GitHub, Slack, AWS, Telegram)
- Чувствительные OAuth/token файлы и token-like значения в текстовых файлах
- Docker network exposure для чувствительных сервисов
- Path traversal в `add-user.sh`
- Реальные секреты в `.env.example`

`.github/semgrep/ai-security.yml` сейчас содержит 14 Semgrep-style AI/security rules.

Текущая версия: [VERSION](VERSION) · [CHANGELOG](CHANGELOG.md) · [Releases](https://github.com/example-org/cortex-forge/releases)

---

## Заметки по безопасности

CortexForge содержит несколько полезных security experiments, но это не production security model:

- **Quota key pattern** — сгенерированные user-инстансы используют `QUOTA_KEY_*`, а не прямой upstream API key
- **Сегментация сетей** — `corp-internal` и `corp-admin` internal Docker-сети, а `corp-outbound` разрешает Telegram/external calls
- **Constant-time сравнение токенов** — bearer token checks используют `hmac.compare_digest`
- **Rate limiting и message limits** — реализованы в proxy/broker paths
- **Resource limits** — лимиты CPU/RAM заданы через Compose `deploy.resources`
- **Опасная admin-мощность по дизайну** — admin-инстанс монтирует весь проект в `/infra` и имеет Docker socket access
- **Audit/quota data** — SQLite используется для quota, broker, monitor и service-agent state

Используй [docs/SECURITY.md](docs/SECURITY.md) как threat-model заметку, не как сертификацию или production hardening guarantee.

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

### quota-proxy / CLIProxyAPI не могут выполнить upstream call

Проверь, что `quota-proxy` и CLIProxyAPI подключены к сети `corp-egress`:
```bash
docker inspect corp-quota | grep -A5 Networks
docker inspect corp-cliproxyapi | grep -A5 Networks
```

У обоих должна быть `corp-egress`. Если в volume CLIProxyAPI нет OAuth credential, сначала выполни OAuth bootstrap. Если сети неверные — выполни `make deploy` для пересоздания с актуальным `docker-compose.yml`.

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
