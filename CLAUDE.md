# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**CortexForge** — корпоративная AI-инфраструктура на базе [OpenClaw](https://github.com/openclaw/openclaw): каждому сотруднику выдаётся изолированный Telegram-бот с собственной памятью, квотой токенов и персонажем. Разворачивается одной командой на одном сервере через Docker Compose.

## Commands

### Development

```bash
make deploy                          # docker compose up -d --build
make status                          # docker compose ps
make logs NAME=admin                 # логи конкретного инстанса
make restart NAME=admin              # перезапустить один инстанс
make install-hooks                   # post-merge hook: авто-ребилд при git pull
```

### Tests

```bash
pytest tests/ -v                     # все тесты (unittest, запускаются через pytest)
pytest tests/test_broker_persistence.py -v   # один файл
```

Тесты поднимают реальные `HTTPServer`-ы с моками и не требуют Docker.

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
make set-limit NAME=user-2 LIMIT=500000
make quota-reset NAME=user-2
```

### User management

```bash
make add-user NAME=user-2 BOT_TOKEN=7xxx FULL_NAME="Пользователь 2" TG_ID=123456789
make remove-user NAME=user-2
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

| Компонент | Путь | Контейнер | Порт |
|-----------|------|-----------|------|
| `quota-proxy` | `quota-proxy/proxy.py` | `corp-quota` | `127.0.0.1:9090` |
| `broker` | `broker/broker.py` | `corp-broker` | — |
| `resource-monitor` | `resource-monitor/monitor.py` | `corp-monitor` | `127.0.0.1:9091` |
| `service-agent` | `service-agent/server.py` | `corp-service` | `127.0.0.1:8090` |
| `instances/admin` | Инстанс Admin | `corp-admin` | `127.0.0.1:18789` |

### How user instances are added

`make add-user` генерирует конфиг в **`docker-compose.override.yml`** (gitignored), а не в основной `docker-compose.yml`. Docker Compose автоматически мержит оба файла. Пользовательские инстансы собираются из `instances/Dockerfile.user` (OpenClaw + ffmpeg + tesseract-ocr + mcporter).

### Service-agent skills

| Скилл | Путь | Назначение |
|-------|------|------------|
| `compliance` | `service-agent/skills/compliance/` | Проверка контрагентов через DaData |
| `corp-messenger` | `service-agent/skills/corp-messenger/` | Межинстансный мессенджер через broker |
| `admin-dashboard` | `service-agent/skills/admin-dashboard/` | Единый центр управления (quota + monitor + broker) |
| `qmd` | `service-agent/skills/qmd/` | Полнотекстовый поиск по markdown файлам |

Скиллы могут использовать `run.py` (Python) или `run.sh` (Bash) — сервер пробует оба. Только env vars, перечисленные в `skills.json` → `env_vars`, передаются в subprocess через `build_skill_env()`.

### Shared skills vs personal skills

- **Shared**: `shared/skills/<name>/SKILL.md` — доступны всем инстансам
- **Personal**: `workspace/skills/<name>/SKILL.md` — только одному инстансу
- Adminитет: personal > shared. Документация: `shared/docs/common/SKILLS.md`

### Network isolation

Пять сетей Docker с намеренной изоляцией:

- **`corp-egress`** — только `quota-proxy` имеет выход в интернет (к `api.anthropic.com`)
- **`corp-internal`** (`internal: true`) — все инстансы + broker; нет внешнего роутинга
- **`corp-admin`** (`internal: true`) — quota-proxy + monitor; нет внешнего роутинга
- **`corp-services`** — service-agent (backend-интеграции)
- **`corp-outbound`** — admin + инстансы (Telegram, внешние API)

**Ключевой принцип:** инстансы не могут напрямую достучаться до Anthropic API. Все запросы идут через `quota-proxy`, который подставляет реальный ключ.

### Security model

- Инстансы используют `QUOTA_KEY_<name>` (SHA256-хэш) вместо реального API-ключа
- Все токен-сравнения через `hmac.compare_digest()` (constant-time)
- Leaky bucket rate-limiting на всех публичных эндпоинтах
- Все контейнеры — non-root user `app`, `no-new-privileges: true`
- `quota-proxy` и `broker` — `read_only: true` (tmpfs для /tmp)
- Квоты и метрики хранятся в SQLite (WAL mode) — переживают рестарты

### Instance workspace structure

```
instances/<name>/workspace/
  SOUL.md           # персонаж и стиль общения
  IDENTITY.md       # имя, эмодзи, вайб
  USER.md           # контекст сотрудника (роль, часовой пояс)
  AGENTS.md         # доступные агенты
  TOOLS.md          # SSH-хосты, личные API-ключи, инструкции к personal skills
  HEARTBEAT.md      # задачи для периодических проверок (пустой = skip)
  memory/           # долгосрочная память
  skills/           # personal skills (приоритет над shared)
  .migrations_applied  # трекинг миграций (gitignored)
openclaw.json       # конфиг: Telegram-канал + модель
```

### Admin instance (Admin)

- Имя: **Admin**. Имеет прямой `ANTHROPIC_API_KEY` (не через quota-proxy)
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
3. Добавить `skills.json` манифест (образец: `compliance/skills.json`). Секреты — в поле `env_vars`
4. Передать переменные в контейнер `assistant-service` через `docker-compose.yml`
5. `docker compose build assistant-service && docker compose restart assistant-service`

## Code conventions

- **Python stdlib only** — никаких внешних зависимостей в core-компонентах (`quota-proxy`, `broker`, `resource-monitor`, `service-agent`)
- **Conventional Commits**: `feat`, `fix`, `docs`, `ci`, `security`, `perf`, `refactor`, `chore`, `test`, `build`, `revert`, `infra`
- Допустимые scopes: `broker`, `quota`, `proxy`, `service`, `monitor`, `mcp`, `scripts`, `docker`, `deps`, `auth`, `api`
- **Squash merge** в `master`
- Все `.env`-файлы должны иметь права `600`; `make security-check` это проверяет

## CI/CD

- **`security.yml`** — Semgrep (+ кастомные правила в `.github/semgrep/`), Bandit, Trivy, Gitleaks, Hadolint, ShellCheck, pip-audit + `ai_security_check.py`
- **`lint-commits.yml`** — Conventional Commits + валидация PR title (`amannn/action-semantic-pull-request`). `WIP:` prefix разрешён
- **`release-please.yml`** — автоматический PR с version bump и `CHANGELOG.md`
- **`release.yml`** — при tag push (`v*`): security checks → build Docker images → push to GHCR (`ghcr.io/<owner>/cortexforge-<service>`) → SBOM (SPDX) → GitHub Release
- Правило: PR нельзя мёрджить с красными security-checks
- CODEOWNERS: `@example-maintainer`. Критичные файлы (`proxy.py`, `broker.py`, `docker-compose.yml`, `security.yml`) требуют явного review

## Configuration

Переменные в корневом `.env` (шаблон: `.env.example`):
- `ANTHROPIC_API_KEY` — только здесь, только для `quota-proxy`
- `ANTHROPIC_REFRESH_TOKEN` — для OAuth-режима (Claude Max вместо API key)
- `QUOTA_ADMIN_TOKEN` — 32+ символов
- `QUOTA_KEY_<NAME>`, `QUOTA_LIMIT_<NAME>`, `BROKER_KEY_<NAME>` — генерируются скриптом `add-user.sh`
- `QUOTA_DEFAULT_MONTHLY` — дефолтная месячная квота (default: 1,000,000)
- `BROKER_KEY_SERVICE` — ключ service-agent для broker
- `SERVICE_API_KEY` — ключ для service-agent API
- `MONITOR_ADMIN_TOKEN` — ключ для resource-monitor API
- `DOCKER_GID` — GID группы docker на хосте (default: 999, для resource-monitor)

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
