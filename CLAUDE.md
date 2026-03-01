# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**CortexForge** — корпоративная AI-инфраструктура на базе [OpenClaw](https://github.com/openclaw/openclaw): каждому сотруднику выдаётся изолированный Telegram-бот с собственной памятью, квотой токенов и персонажем. Разворачивается одной командой на одном сервере через Docker Compose.

## Commands

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
```

### Security checks (required before PRs)

```bash
python3 .github/scripts/ai_security_check.py   # 8 AI-specific security rules
shellcheck scripts/*.sh                          # shell script linting
make security-check                              # проверка .env-прав, ключей, gitignore
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
```

### Monitoring & service-agent

```bash
make monitor                           # CPU/RAM/disk метрики
make monitor-alerts                    # активные алерты
make service-health                    # healthcheck service-agent
make service-skills                    # список скиллов
```

## Architecture

### Core components

| Компонент | Путь | Назначение |
|-----------|------|------------|
| `quota-proxy` | `quota-proxy/proxy.py` | Единственный держатель `ANTHROPIC_API_KEY`; квотирование, rate-limit, аудит |
| `broker` | `broker/broker.py` | In-memory шина сообщений между инстансами |
| `resource-monitor` | `resource-monitor/monitor.py` | Метрики Docker-контейнеров, алерты в broker |
| `service-agent` | `service-agent/server.py` | HTTP API для вызова скиллов (stdin→stdout JSON) |
| `instances/admin` | `instances/admin/` | Инстанс Prior — инфраструктурный контроль, прямой `ANTHROPIC_API_KEY` |
| `instances/_template` | `instances/_template/` | Шаблон для новых инстансов |

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
- Все токен-сравнения через `hmac.compare_digest()` (constant-time, защита от timing-атак)
- Leaky bucket rate-limiting на всех публичных эндпоинтах
- Все контейнеры — non-root user `app`, `no-new-privileges: true`
- Квоты и метрики хранятся в SQLite (WAL mode) — переживают рестарты без ребилда

### Instance workspace structure

Каждый инстанс — OpenClaw-контейнер с workspace:
```
instances/<name>/workspace/
  SOUL.md       # персонаж и стиль общения
  IDENTITY.md   # имя, эмодзи, вайб
  USER.md       # контекст сотрудника (роль, часовой пояс)
  AGENTS.md     # доступные агенты
  memory/       # долгосрочная память
openclaw.json   # конфиг: Telegram-канал + модель
```

### Adding a skill to service-agent

1. Создать `service-agent/skills/<skill-name>/`
2. Реализовать `run.py`: читает JSON из stdin, пишет JSON в stdout
3. Добавить `skills.json` манифест (см. `compliance/skills.json` как образец)
4. `docker compose build assistant-service && docker compose restart assistant-service`

## Code conventions

- **Python stdlib only** — никаких внешних зависимостей в core-компонентах (`quota-proxy`, `broker`, `resource-monitor`, `service-agent`)
- **Conventional Commits**: `feat:`, `fix:`, `docs:`, `ci:`, `security:`, `perf:`, `refactor:` — CI отклонит нарушающие PR
- **Squash merge** в `master`
- Все `.env`-файлы должны иметь права `600`; `make security-check` это проверяет

## CI/CD

- **`security.yml`** — Semgrep, CodeQL, Trivy, Gitleaks, Hadolint, ShellCheck + `ai_security_check.py` (8 кастомных правил)
- **`lint-commits.yml`** — проверка Conventional Commits
- **`release-please.yml`** — автоматически открывает PR с version bump и обновлением `CHANGELOG.md`
- Правило: PR нельзя мёрджить с красными security-checks

## Configuration

Переменные в корневом `.env` (шаблон: `.env.example`):
- `ANTHROPIC_API_KEY` — только здесь, только для `quota-proxy`
- `QUOTA_ADMIN_TOKEN` — 32+ символов
- `QUOTA_KEY_<NAME>`, `QUOTA_LIMIT_<NAME>`, `BROKER_KEY_<NAME>` — генерируются скриптом `add-user.sh`

Переменные инстанса в `instances/<name>/.env`:
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOW_FROM`
- `BROKER_KEY` — берётся из корневого `.env`