# Замена upstream quota-proxy на CLIProxyAPI + обновление характера помощников

## Overview

Две задачи:
  1. Добавить CLIProxyAPI как Docker-сервис и перенастроить quota-proxy форвардить запросы через него вместо api.anthropic.com - это позволит использовать OAuth-подписку Claude Max вместо платного API-ключа.
  2. Переработать SOUL.md и IDENTITY.md шаблоны - сделать помощников тёплыми, участливыми обезьянками, которые предлагают workaround'ы когда заходят в тупик.

## Context

- Files involved:
  - `docker-compose.yml` - добавление сервиса cliproxyapi, обновление сети
  - `quota-proxy/proxy.py` - замена UPSTREAM на configurable, изменение auth-заголовков
  - `quota-proxy/Dockerfile` - без изменений (если не нужны зависимости)
  - `instances/_template/workspace/SOUL.md` - новый характер помощников
  - `instances/_template/workspace/IDENTITY.md` - обновление vibe
  - `instances/admin/workspace/SOUL.md` - обновление для admin
  - `.env.example` - новые переменные для CLIProxyAPI
  - `scripts/add-user.sh` - без изменений (уже использует openclaw.json template)
- Related patterns: Docker services в docker-compose.yml, env-переменные через .env
- Dependencies: CLIProxyAPI Docker image `eceasy/cli-proxy-api:latest`

## Development Approach

- **Testing approach**: Regular (code first, then tests)
- Complete each task fully before moving to the next
- **CRITICAL: every task MUST include new/updated tests**
- **CRITICAL: all tests must pass before starting next task**

## Implementation Steps

### Task 1: Добавить CLIProxyAPI как Docker-сервис

**Files:**
- Modify: `docker-compose.yml`
- Create: `cliproxyapi/config.yaml`
- Modify: `.env.example`

- [x] Создать директорию `cliproxyapi/` с `config.yaml`:
  - host: "0.0.0.0", port: 8317
  - api-keys: берётся из env-переменной CLIPROXY_API_KEY
  - logging-to-file: true
  - commercial-mode: true (меньше RAM)
- [x] Добавить сервис `cliproxyapi` в docker-compose.yml:
  - image: eceasy/cli-proxy-api:latest
  - volumes: ./cliproxyapi/config.yaml:/CLIProxyAPI/config.yaml, cliproxyapi-auths:/root/.cli-proxy-api, cliproxyapi-logs:/CLIProxyAPI/logs
  - networks: corp-egress (для OAuth), corp-internal (для quota-proxy)
  - port: не экспонировать наружу (только internal)
  - depends_on: ничего (самостоятельный сервис)
  - healthcheck: curl http://localhost:8317/v1/models
- [x] Добавить в .env.example переменные CLIPROXY_API_KEY
- [x] Добавить volume cliproxyapi-auths и cliproxyapi-logs
- [x] Написать тест на валидацию конфига cliproxyapi (проверка формата config.yaml)
- [x] Запустить тесты - должны пройти

### Task 2: Перенастроить quota-proxy на CLIProxyAPI upstream

**Files:**
- Modify: `quota-proxy/proxy.py`

- [x] Добавить env-переменную UPSTREAM_URL (default: "https://api.anthropic.com") - заменить хардкод UPSTREAM
- [x] Добавить env-переменную UPSTREAM_API_KEY (default: REAL_API_KEY) - ключ для upstream (CLIProxyAPI api-key или реальный Anthropic ключ)
- [x] Изменить метод _proxy():
  - Вместо хардкода REAL_API_KEY использовать UPSTREAM_API_KEY
  - Вместо хардкода UPSTREAM использовать UPSTREAM_URL
  - Если UPSTREAM_URL != api.anthropic.com, не добавлять OAuth beta-заголовки
  - Добавить User-Agent header "claude-cli/2.1.44 (external, sdk-cli)" при работе через CLIProxyAPI (нужен чтобы CLIProxyAPI не включал cloaking)
- [x] Обновить docker-compose.yml: передать UPSTREAM_URL=http://cliproxyapi:8317 и UPSTREAM_API_KEY=${CLIPROXY_API_KEY} в quota-proxy
- [x] Сделать quota-proxy depends_on cliproxyapi (с healthcheck)
- [x] Оставить ANTHROPIC_API_KEY опциональным - если задан, proxy может использовать его как fallback (но в этой итерации просто конфигурируемый upstream)
- [x] Написать тесты для нового поведения proxy (mock upstream URL, проверка заголовков)
- [x] Запустить тесты - должны пройти

### Task 3: Обновить характер помощников в SOUL.md

**Files:**
- Modify: `instances/_template/workspace/SOUL.md`
- Modify: `instances/_template/workspace/IDENTITY.md`

- [x] Переписать SOUL.md - сохранить обезьянью тематику, но добавить:
  - Участливость: помощник искренне хочет помочь, не просто выполняет команды
  - Workaround-мышление: при тупике всегда предлагает альтернативный путь ("Напрямую не получится, но можно вот так...")
  - Тёплый тон: не сухой "Нет.", а "Хм, тут загвоздка. Но есть обходной путь:"
  - Сохранить прямолинейность (без воды), но убрать холодность
  - Обезьянье любопытство остаётся, но добавляется забота о результате пользователя
- [x] Обновить IDENTITY.md - изменить vibe на "участливый, находчивый, немного озорной"
- [x] НЕ трогать instances/admin/workspace/SOUL.md - admin остаётся со своим характером
- [x] Написать простой тест-валидатор что SOUL.md содержит ключевые секции (workaround, участливость)
- [x] Запустить тесты - должны пройти

### Task 4: Verify acceptance criteria

- [ ] Manual test: docker compose config --services показывает cliproxyapi
- [ ] Manual test: quota-proxy использует configurable UPSTREAM_URL
- [ ] Manual test: SOUL.md содержит инструкции про workaround'ы и участливый тон
- [ ] Run full test suite
- [ ] Run linter (shellcheck scripts/*.sh)
- [ ] Run security check (python3 .github/scripts/ai_security_check.py)

### Task 5: Update documentation

- [ ] Обновить CLAUDE.md - добавить CLIProxyAPI в архитектуру, новые env-переменные
- [ ] Обновить .env.example с комментариями
- [ ] Переместить план в docs/plans/completed/
