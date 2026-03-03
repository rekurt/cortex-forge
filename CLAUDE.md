# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**CortexForge** — корпоративная AI-инфраструктура на базе [OpenClaw](https://github.com/openclaw/openclaw): каждому сотруднику выдаётся изолированный Telegram-бот с собственной памятью, квотой токенов и персонажем. Разворачивается одной командой на одном сервере через Docker Compose.

## Commands

### Prerequisites

Docker 24+, Docker Compose 2.x, Python 3.12+, ShellCheck.

### Development

```bash
# Запустить/пересобрать всё
make deploy                          # docker compose up -d --build
docker compose ps                    # статус контейнеров
make status                          # то же самое

# Логи конкретного инстанса
make logs NAME=admin

# Перезапустить один инстанс
make restart NAME=admin

# Установить git hooks (post-merge: автоматические миграции при git pull)
make install-hooks
```

### Testing

Тесты поднимают реальные `HTTPServer`-ы с моками и не требуют Docker. Используют `unittest` из stdlib (pytest опционален).

```bash
# Все тесты
python3 -m pytest tests/ -v
python3 -m unittest discover tests/       # без pytest

# Один тестовый модуль
python3 -m pytest tests/test_broker_persistence.py -v
python3 tests/test_broker_persistence.py               # напрямую

# Один тест
python3 -m pytest tests/test_broker_persistence.py::TestBrokerPersistence::test_send_and_receive -v
```

**Паттерны тестов:** серверы запускаются в daemon-потоках через `setUpClass` на port 0 (OS выбирает свободный). Env-переменные переопределяются до импорта тестируемого модуля. БД-файлы (`.db`, `-wal`, `-shm`) чистятся в `tearDownClass`. Скиллы тестируются через stdin/stdout JSON subprocess.

### Security checks (required before PRs)

```bash
python3 .github/scripts/ai_security_check.py   # 8 AI-specific security rules (Semgrep-like)
shellcheck scripts/*.sh                          # shell script linting
make security-check                              # .env-права (600), ключи, gitignore
```

### Quota management

```bash
make quota-report                      # использование токенов за текущий месяц
make quota-report MONTH=2026-03        # за конкретный месяц
make set-limit NAME=alexey LIMIT=500000  # изменить лимит без рестарта
make quota-reset NAME=alexey           # сбросить счётчик
```

### User management

```bash
make add-user NAME=alexey BOT_TOKEN=7xxx FULL_NAME="Алексей" TG_ID=123456789
make remove-user NAME=alexey
make backup                            # архивировать все воркспейсы
make add-service NAME=svc-kyc PORT=8091 SKILLS=compliance,kyc  # реплика service-agent
```

### Monitoring & service-agent

```bash
make monitor                           # CPU/RAM/disk метрики
make monitor-alerts                    # активные алерты
make service-health                    # healthcheck service-agent
make service-skills                    # список скиллов
make admin-overview                    # сводка quota + monitor + broker
```

### Migrations

```bash
python3 scripts/migrate-instances.py             # применить все новые миграции
python3 scripts/migrate-instances.py --dry-run   # посмотреть что изменится
```

Миграции запускаются автоматически при `git pull` (через post-merge hook).

## Architecture

### Core components

| Компонент | Путь | Назначение |
|-----------|------|------------|
| `cliproxyapi` | `cliproxyapi/config.yaml` | OAuth-прокси для Claude Max; позволяет использовать подписку вместо API-ключа |
| `quota-proxy` | `quota-proxy/proxy.py` | Квотирование, rate-limit, аудит; форвардит запросы через configurable upstream (CLIProxyAPI или напрямую в Anthropic API) |
| `broker` | `broker/broker.py` | Шина сообщений между инстансами (SQLite persistence) |
| `resource-monitor` | `resource-monitor/monitor.py` | Метрики Docker-контейнеров, алерты в broker |
| `service-agent` | `service-agent/server.py` | HTTP API для вызова скиллов (stdin→stdout JSON); лимит 5 параллельных задач, таймаут 120s |
| `instances/admin` | `instances/admin/` | Инстанс Prior — инфраструктурный контроль, прямой `ANTHROPIC_API_KEY` |
| `instances/_template` | `instances/_template/` | Шаблон для новых инстансов |

### Service-agent skills

| Скилл | Путь | Назначение |
|-------|------|------------|
| `compliance` | `service-agent/skills/compliance/` | Проверка контрагентов через DaData |
| `corp-messenger` | `service-agent/skills/corp-messenger/` | Межинстансный мессенджер через broker |
| `admin-dashboard` | `service-agent/skills/admin-dashboard/` | Единый центр управления (quota + monitor + broker) |
| `qmd` | `service-agent/skills/qmd/` | Полнотекстовый поиск по markdown файлам |

### Personal skills

Каждый инстанс может иметь личные скиллы в `workspace/skills/`. Приоритет: personal skills > shared skills. Документация: `shared/docs/common/SKILLS.md`.

### Network isolation

Пять сетей Docker с намеренной изоляцией:

- **`corp-egress`** — `quota-proxy` + `cliproxyapi` имеют выход в интернет (CLIProxyAPI → OAuth Anthropic, quota-proxy → CLIProxyAPI или напрямую в `api.anthropic.com`)
- **`corp-internal`** (`internal: true`) — все инстансы + broker; нет внешнего роутинга
- **`corp-admin`** (`internal: true`) — quota-proxy + monitor; нет внешнего роутинга
- **`corp-services`** — service-agent (backend-интеграции)
- **`corp-outbound`** — admin + инстансы (Telegram, внешние API)

**Ключевой принцип:** инстансы не могут напрямую достучаться до Anthropic API. Все запросы идут через `quota-proxy`, который форвардит их в configurable upstream — по умолчанию через `CLIProxyAPI` (OAuth), но может работать напрямую с `api.anthropic.com`.

### Quota-proxy upstream modes

Три режима, определяются автоматически по `UPSTREAM_URL` и формату ключа:
1. **CLIProxyAPI** — `UPSTREAM_URL` не `api.anthropic.com` → заголовок `x-api-key`, `User-Agent: claude-cli/*`
2. **OAuth** — ключ `sk-ant-oat-*` → добавляет beta-заголовки (`oauth-2025-04-20`, `claude-code-20250219`)
3. **Standard** — прямой `api.anthropic.com` с `x-api-key`

Rate limits: 300 req/min на инстанс, 60 req/min на admin-эндпоинты.

### Security model

- Инстансы используют `QUOTA_KEY_<name>` (SHA256-хэш) вместо реального API-ключа
- Все токен-сравнения через `hmac.compare_digest()` (constant-time, защита от timing-атак)
- Leaky bucket rate-limiting на всех публичных эндпоинтах
- Все контейнеры — non-root user `app`, `no-new-privileges: true`
- Квоты и метрики хранятся в SQLite (WAL mode) — переживают рестарты без ребилда

### Instance workspace structure

Каждый инстанс — OpenClaw-контейнер с workspace:
```
instances/<name>/workspace/
  SOUL.md           # персонаж и стиль общения
  IDENTITY.md       # имя, эмодзи, вайб
  USER.md           # контекст сотрудника (роль, часовой пояс)
  TOOLS.md          # инструкции по инструментам, SSH-хосты, личные скиллы
  AGENTS.md         # доступные агенты
  skills/           # личные скиллы (приоритет над shared)
  HEARTBEAT.md      # задачи для периодических проверок (пустой = skip)
  memory/           # долгосрочная память
  .migrations_applied  # трекинг миграций (gitignored)
openclaw.json       # конфиг: Telegram-канал + модель
```

### Admin instance (Prior)

- Имя: **Приор**. Имеет прямой `ANTHROPIC_API_KEY` (не через quota-proxy)
- Доступ к Docker socket (read-only) и всем workspace-ам через `/infra/instances`
- Ежечасно запускает `scripts/sync-instances.sh`: миграции, healthcheck, рестарт упавших контейнеров

### Broker API

- `POST /send` — отправить сообщение (sender определяется по API-ключу, не по body)
- `GET /inbox` — прочитать входящие
- `DELETE /inbox` — очистить inbox
- Лимиты: 10 KB/сообщение, 100 сообщений в inbox, 24 часа retention

### Migrations

Файлы в `migrations/NNN_description.py`. Каждый содержит:
- `DESCRIPTION: str`
- `apply(workspace: pathlib.Path)` — **должна быть idempotent** (проверять перед записью)

Правила: не трогать личные файлы (`MEMORY.md`, `memory/`, кастомизированные `USER.md`, `SOUL.md`). Overrides: `../overrides/migrations/` (приоритет над репо). После применения — session cache (`.jsonl`) очищается и инстанс перезапускается.

### Adding a skill to service-agent

1. Создать `service-agent/skills/<skill-name>/`
2. Реализовать `run.py`: читает JSON из stdin, пишет JSON в stdout
3. Добавить `skills.json` манифест (см. `compliance/skills.json` как образец). Если скиллу нужны секреты из окружения (API-ключи и т.п.), объяви их в поле `env_vars` — только они будут переданы в subprocess (`build_skill_env()` в `server.py`). Переменная также должна быть передана в контейнер `assistant-service` через `docker-compose.yml`.
4. `docker compose build assistant-service && docker compose restart assistant-service`

## Code conventions

- **Python stdlib only** — никаких внешних зависимостей в core-компонентах (`quota-proxy`, `broker`, `resource-monitor`, `service-agent`)
- **Conventional Commits**: `feat`, `fix`, `docs`, `ci`, `security`, `perf`, `refactor`, `chore`, `test`, `build`, `revert`, `infra`
- Допустимые scopes: `broker`, `quota`, `proxy`, `service`, `monitor`, `mcp`, `scripts`, `docker`, `deps`, `auth`, `api`
- **Squash merge** в `master`
- Все `.env`-файлы должны иметь права `600`; `make security-check` это проверяет

## CI/CD

- **`security.yml`** — Semgrep, CodeQL, Trivy, Gitleaks, Hadolint, ShellCheck + `ai_security_check.py` (8 кастомных правил)
- **`lint-commits.yml`** — проверка Conventional Commits
- **`release-please.yml`** — автоматически открывает PR с version bump и обновлением `CHANGELOG.md`
- Правило: PR нельзя мёрджить с красными security-checks
- CODEOWNERS: `@rekurt`. Критичные файлы (`proxy.py`, `broker.py`, `docker-compose.yml`, `security.yml`) требуют явного review

## Configuration

Переменные в корневом `.env` (шаблон: `.env.example`):
- `ANTHROPIC_API_KEY` — обязателен для admin-инстанса (ходит напрямую); для остальных опционален при использовании CLIProxyAPI
- `CLIPROXY_API_KEY` — ключ авторизации quota-proxy → CLIProxyAPI (генерируется: `python3 -c "import secrets; print('clip-' + secrets.token_urlsafe(24))"`)
- `QUOTA_ADMIN_TOKEN` — 32+ символов
- `QUOTA_KEY_<NAME>`, `QUOTA_LIMIT_<NAME>`, `BROKER_KEY_<NAME>` — генерируются скриптом `add-user.sh`
- `BROKER_KEY_SERVICE` — ключ service-agent для доступа к broker (corp-messenger skill)
- `BROKER_KEY_MONITOR` — ключ resource-monitor для отправки алертов в broker
- `SERVICE_API_KEY` — ключ для авторизации запросов к service-agent API

Переменные инстанса в `instances/<name>/.env`:
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOW_FROM`
- `BROKER_KEY` — берётся из корневого `.env`

Пороги алертов resource-monitor (env vars): `ALERT_CPU_PCT` (80%), `ALERT_RAM_PCT` (85%), `ALERT_DISK_PCT` (90%), `ALERT_QUOTA_PCT` (80%), `MONITOR_INTERVAL` (60s).

### Key operational scripts

| Скрипт | Назначение |
|--------|------------|
| `scripts/autoupdate.sh` | Cron-скрипт (каждые 5 мин): git pull + rebuild changed |
| `scripts/sync-instances.sh` | Ежечасный maintenance от admin: миграции, healthcheck |
| `scripts/fix-permissions.sh` | Восстановить права 600 на .env после git-операций |
| `scripts/refresh-anthropic-token.sh` | Обновить OAuth-токен из `ANTHROPIC_REFRESH_TOKEN` |
| `scripts/migrate-instances.py` | Применить миграции ко всем инстансам |

## Gotchas

- **Port assignment**: `add-user.sh` авто-назначает порт как `18790 + N` (N = количество существующих инстансов)
- **Session cache**: после применения миграций `.jsonl`-файлы кэша **удаляются**, чтобы агент перечитал конфиги
- **Skills env isolation**: service-agent передаёт subprocess только переменные из `env_vars` в `skills.json` — остальные env не попадают в скилл
- **SQLite WAL**: все компоненты используют WAL mode + `journal_size_limit=1048576` (1MB); данные переживают рестарт контейнера
- **Broker sender auth**: отправитель определяется по API-ключу, не по полю body — подменить sender невозможно
