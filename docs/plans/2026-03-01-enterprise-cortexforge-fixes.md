# Enterprise CortexForge: исправление проблем и enterprise-готовность

## Overview

Комплексный план превращения CortexForge в полноценное enterprise-решение. Исправляет критические баги (ключи, сети,
мессенджер), дает Приору обширную базу знаний чтобы он перестал ломать инфраструктуру, добавляет
персистентность брокеру, admin-dashboard, qmd-поиск по markdown и инфраструктуру личных скиллов.

Выявленные проблемы:
- CRITICAL: add-user.sh (строка 143) передает ANTHROPIC_API_KEY=${{ANTHROPIC_API_KEY}} (двойные скобки = literal string, ключ не подставляется) — новые инстансы вообще не могут авторизоваться
- CRITICAL: существующие инстансы (nikita, vasily, dmitry) на сети corp-egress вместо corp-outbound — имеют прямой интернет-доступ через сеть quota-proxy
- CRITICAL: corp-messenger имеет только SKILL.md документацию, но НЕТ run.py — скилл не исполняемый, мессенджер физически не работает
- CRITICAL: Приор путается в ключах и ломает quota-proxy, потому что в AGENTS.md недостаточно конкретики про архитектуру ключей (ANTHROPIC_API_KEY в openclaw.json это НЕ реальный ключ для инстансов, а QUOTA_KEY через env mapping)
- RELIABILITY: broker in-memory (collections.deque) — сообщения пропадают при рестарте
- MISSING: нет единого центра управления (admin-dashboard)
- MISSING: нет qmd-поиска по markdown файлам
- MISSING: нет личных скиллов (только shared)

## Context

- Files involved:
  - `scripts/add-user.sh` — баг с двойными скобками на строке 143-144
  - `docker-compose.yml` — сети corp-egress/corp-outbound для инстансов (строки 252-254, 283-285, 318-320)
  - `instances/admin/workspace/AGENTS.md` — главный контекст Приора (272 строки, нужна переработка)
  - `instances/admin/workspace/TOOLS.md` — пустой шаблон, не используется Приором
  - `shared/skills/corp-messenger/SKILL.md` — документация без реализации
  - `broker/broker.py` — in-memory deque (182 строки)
  - `service-agent/server.py` — skill execution engine
  - `service-agent/skills/` — только compliance/, нет corp-messenger/
  - `instances/_template/` — шаблон workspace
  - `Makefile` — управление
- Related patterns: Python stdlib only, Docker Compose, SQLite WAL, hmac.compare_digest()
- Dependencies: нет внешних (stdlib only)

## Development Approach

- **Testing approach**: Regular (код сначала, docker compose тестирование)
- Каждый таск — один логический компонент
- После каждого таска: docker compose build && docker compose up -d && проверка логов
- **CRITICAL: каждый таск завершается проверкой docker compose ps и логов**
- **CRITICAL: security-checks должны проходить перед финальным мёрджем**

## Implementation Steps

### Task 1: Починить ключи, сети и add-user.sh (SECURITY/CRITICAL)

Три связанных бага, которые вместе ломали quota-proxy:

**Баг 1 — add-user.sh двойные скобки:**
Строка 143: `ANTHROPIC_API_KEY=${{ANTHROPIC_API_KEY}}` — двойные скобки в Python f-string дают literal `${ANTHROPIC_API_KEY}`. Docker Compose интерпретирует
это как переменную окружения хоста, подставляет РЕАЛЬНЫЙ Anthropic ключ. Инстансы получают настоящий ключ
вместо QUOTA_KEY — обходят квотную систему.

**Баг 2 — сети существующих инстансов:**
nikita/vasily/dmitry на `corp-egress` (строки 254, 285, 320) — это сеть для выхода quota-proxy в интернет. Инстансы должны быть на
`corp-outbound` (Telegram + внешние API).

**Баг 3 — add-user.sh не монтирует compliance-data:**
Шаблон в add-user.sh не добавляет `./shared/compliance-data:/shared/compliance-data:ro`, хотя вручную созданные инстансы в docker-compose.yml это
имеют.

**Files:**
- Modify: `scripts/add-user.sh` (строки 142-147)
- Modify: `docker-compose.yml` (строки 252-254, 283-285, 318-320)

- [x] В add-user.sh строка 143: заменить `ANTHROPIC_API_KEY=${{ANTHROPIC_API_KEY}}` на `ANTHROPIC_API_KEY=${{{f"QUOTA_KEY_{NAME_UPPER}"}}}` — инстанс получит свой QUOTA_KEY через Docker Compose variable substitution
- [x] В add-user.sh строка 144: удалить `OPENAI_API_KEY=${{OPENAI_API_KEY}}` (инстансы не должны иметь прямой OpenAI ключ)
- [x] В add-user.sh: добавить volume mount `./shared/compliance-data:/shared/compliance-data:ro`
- [x] В docker-compose.yml: для assistant-nikita, assistant-vasily, assistant-dmitry заменить `corp-egress` на `corp-outbound` в секции networks
- [x] docker compose up -d && проверить логи quota-proxy: инстансы должны авторизоваться через QUOTA_KEY
- [x] Проверить что инстансы НЕ имеют прямого доступа к api.anthropic.com (только через proxy)

### Task 2: Полная база знаний Приора — AGENTS.md + TOOLS.md (CRITICAL)

Приор постоянно путается в ключах и ломает инфраструктуру. Причина: AGENTS.md описывает архитектуру в общих
чертах, но не дает конкретных "НИКОГДА НЕ ДЕЛАЙ" правил и не объясняет критический нюанс: openclaw.json говорит `apiKey:
${ANTHROPIC_API_KEY}`, но для инстансов значение этой env-переменной = QUOTA_KEY (через Docker Compose mapping `ANTHROPIC_API_KEY=${QUOTA_KEY_NIKITA}`).
Нужно переписать документацию так, чтобы Приор физически не мог перепутать ключи.

**Files:**
- Modify: `instances/admin/workspace/AGENTS.md` (переработать секции про ключи и инфраструктуру)
- Modify: `instances/admin/workspace/TOOLS.md` (заполнить реальным инфра-контекстом)

- [x] В AGENTS.md добавить секцию "DANGER ZONE — Ключи и Tokens" с конкретной таблицей:

  Таблица "Карта ключей CortexForge":

  | Переменная | Где живёт | Значение | Кто использует |
  |---|---|---|---|
  | ANTHROPIC_API_KEY (в .env корня) | Только в quota-proxy | sk-ant-xxx (реальный ключ) | quota-proxy для форвардинга |
  | ANTHROPIC_API_KEY (в docker env инстанса) | docker-compose.yml | = QUOTA_KEY_NIKITA (НЕ реальный ключ!) | OpenClaw через openclaw.json |
  | QUOTA_KEY_NIKITA (в .env корня) | docker-compose.yml env mapping | quota-nikita-xxx (хэшируется в proxy) | Подставляется как ANTHROPIC_API_KEY |
  | QUOTA_ADMIN_TOKEN | Только Приор и quota-proxy | 32+ символов | Admin API quota-proxy |
  | BROKER_KEY_* | Broker + каждый инстанс | Рандомная строка (хэшируется в broker) | Аутентификация в мессенджере |

  Красная зона — НИКОГДА НЕ ДЕЛАЙ:
  - НИКОГДА не копируй ANTHROPIC_API_KEY из корневого .env в инстанс
  - НИКОГДА не редактируй .env файлы вручную через docker — используй скрипты на хосте
  - НИКОГДА не меняй QUOTA_KEY_* в рантайме — нужен docker compose restart
  - НИКОГДА не давай инстансу прямой ключ к Anthropic API

  Зелёная зона — КАК ПРАВИЛЬНО:
  - Добавить инстанс: `cd /infra && make add-user ...` (запускать на хосте или через docker socket exec)
  - Поменять лимит: `cd /infra && bash scripts/quota.sh set-limit <name> <limit>` (без рестарта)
  - Сбросить квоту: `cd /infra && bash scripts/quota.sh reset <name>`
  - Перезапустить инстанс: `docker restart corp-<name>` (через docker.sock)

- [x] В AGENTS.md добавить секцию "Файловая система — полная карта изоляции":

  Таблица "Что видит каждый контейнер":

  | Путь в контейнере | Хост-путь | Права | Кто видит |
  |---|---|---|---|
  | /home/node/.openclaw/ | instances/\<name\>/openclaw_data/ | rw | Свой инстанс |
  | /home/node/.openclaw/workspace/ | ../\<name\>-workspace/ | rw | Свой инстанс |
  | /shared/skills/ | shared/skills/ | ro | Все инстансы |
  | /shared/docs/ | shared/docs/ | rw | Все инстансы |
  | /shared/compliance-data/ | shared/compliance-data/ | ro | Все инстансы |
  | /infra/ | ./ (корень проекта) | rw | ТОЛЬКО Приор |
  | /var/run/docker.sock | /var/run/docker.sock | ro | ТОЛЬКО Приор |

  Важно: все обслуживающие операции (add-user, set-limit, restart, deploy) НАДО выполнять через:
  - Скрипты в /infra/scripts/ (Makefile targets)
  - Docker socket (docker restart, docker logs)
  - НЕ через прямое редактирование файлов инстансов

- [x] В AGENTS.md добавить секцию "Как работает quota-proxy — для понимания":

  Схема потока запроса:
  1. OpenClaw шлёт запрос на baseUrl (http://quota-proxy:9090) с x-api-key = ANTHROPIC_API_KEY (из env = QUOTA_KEY_*)
  2. quota-proxy хэширует ключ через SHA256
  3. Сравнивает с хэшами QUOTA_KEY_* из корневого .env (constant-time)
  4. Если совпал — определяет имя инстанса, проверяет лимит
  5. Подставляет РЕАЛЬНЫЙ sk-ant-xxx ключ и форвардит в api.anthropic.com
  6. Логирует расход токенов в SQLite

  Почему инстансы получают ANTHROPIC_API_KEY = quota key:
  - openclaw.json.template содержит `"apiKey": "${ANTHROPIC_API_KEY}"`
  - Docker Compose маппит: `ANTHROPIC_API_KEY=${QUOTA_KEY_NIKITA}`
  - OpenClaw видит env-переменную ANTHROPIC_API_KEY, подставляет в apiKey
  - Результат: запрос идёт на quota-proxy с quota key, proxy подменяет на реальный

- [x] В TOOLS.md: заполнить реальными данными инфраструктуры вместо пустого шаблона:
  - Текущие инстансы (имена, порты, Telegram боты)
  - IP/порты внутренних сервисов
  - Команды для частых операций
  - Путь к логам и данным
- [x] Создать миграцию `migrations/NNN_update_admin_agents.py` чтобы обновить AGENTS.md Приора
- [x] Очистить сессии Приора после обновления (rm *.jsonl + sessions.json)

### Task 3: Реализовать corp-messenger skill (CRITICAL FIX)

Corp-messenger НЕ РАБОТАЛ. Причина: в `shared/skills/corp-messenger/` есть только SKILL.md (документация с curl-примерами), но НЕТ
исполняемого run.py. service-agent не может загрузить его как скилл. OpenClaw-инстансы видят SKILL.md и пытаются вызвать curl, но
у них нет curl в контейнере (контейнер OpenClaw — Node.js based).

Решение: создать полноценный service-agent skill с run.py, который делает HTTP-вызовы к broker API через Python urllib.

**Files:**
- Create: `service-agent/skills/corp-messenger/run.py`
- Create: `service-agent/skills/corp-messenger/skills.json`
- Modify: `shared/skills/corp-messenger/SKILL.md` (переписать: инстансы вызывают через service-agent, не curl)
- Modify: `docker-compose.yml` (добавить BROKER_URL и BROKER_KEY env vars для service-agent, подключить service-agent к corp-internal)
- Modify: `.env.example` (добавить BROKER_KEY_SERVICE)

- [x] Создать skills.json:
  ```json
  {
    "id": "corp-messenger",
    "name": "Corp Messenger",
    "description": "Межинстансный мессенджер CortexForge",
    "params": {
      "action": {"type": "string", "enum": ["send", "inbox", "clear", "list"], "required": true},
      "to": {"type": "string", "required": false},
      "message": {"type": "string", "required": false}
    },
    "timeout": 30,
    "env_vars": ["BROKER_URL", "BROKER_KEY"]
  }
  ```
- [x] Создать run.py (Python stdlib, urllib.request):
  - action "send": POST /send к BROKER_URL с {to, message}, Authorization: Bearer BROKER_KEY
  - action "inbox": GET /inbox, вернуть список сообщений
  - action "clear": DELETE /inbox, очистить прочитанные
  - action "list": GET /health, показать доступные инстансы (без auth)
  - Обработка ошибок: 403 (bad key), 429 (rate limit), 404 (unknown recipient), network errors
  - Все HTTP через urllib.request.Request (stdlib only, без curl)
- [x] В docker-compose.yml:
  - Добавить service-agent в сеть corp-internal (чтобы достучаться до broker)
  - Добавить environment: BROKER_URL=http://message-broker:8080, BROKER_KEY=${BROKER_KEY_SERVICE}
- [x] В корневом .env: сгенерировать BROKER_KEY_SERVICE, добавить в broker environment
- [x] Переписать shared/skills/corp-messenger/SKILL.md:
  - Убрать curl-примеры (они не работают в OpenClaw контейнерах)
  - Описать вызов через service-agent HTTP API: POST /v1/run с skill_id=corp-messenger
  - Примеры для каждого action
- [x] docker compose build assistant-service message-broker && docker compose up -d
- [x] E2E тест: отправить сообщение через service-agent API, проверить inbox другого инстанса через broker API

### Task 4: Broker persistence — SQLite вместо in-memory (RELIABILITY)

Broker хранит сообщения в collections.deque — при рестарте контейнера всё теряется. Для enterprise-решения нужна
персистентность через SQLite (как уже сделано в quota-proxy и monitor).

**Files:**
- Modify: `broker/broker.py` (deque -> SQLite)
- Modify: `broker/Dockerfile` (добавить /data volume point)
- Modify: `docker-compose.yml` (добавить broker-data volume)

- [x] Добавить SQLite storage в broker.py:
  - Таблица: messages (id INTEGER PK AUTOINCREMENT, sender TEXT, recipient TEXT, body TEXT, ts REAL)
  - WAL mode, journal_size_limit, CREATE TABLE IF NOT EXISTS при старте
  - DB path из env: BROKER_DB (default: /data/broker.db)
- [x] Заменить _inbox defaultdict(deque) на SQLite операции:
  - send: INSERT INTO messages
  - inbox: SELECT * WHERE recipient=? AND ts > cutoff ORDER BY ts LIMIT MAX_INBOX
  - clear: DELETE WHERE recipient=?
  - health: добавить count per recipient
- [x] _cleanup(): DELETE WHERE ts < cutoff (вместо deque iteration)
- [x] MAX_INBOX enforcement: после INSERT — DELETE overflow
- [x] docker-compose.yml:
  - Добавить volume broker-data:/data
  - Добавить BROKER_DB=/data/broker.db в environment
- [x] Тест: отправить сообщения, docker compose restart message-broker, проверить что inbox сохранился

### Task 5: Admin dashboard skill с обширной базой знаний (MANAGEMENT)

Управление фрагментировано: quota-proxy API + resource-monitor API + broker API + Makefile. Нужен единый admin-dashboard skill в service-agent,
агрегирующий данные со всех сервисов. Включает обширную inline-документацию для Приора прямо в ответах.

**Files:**
- Create: `service-agent/skills/admin-dashboard/run.py`
- Create: `service-agent/skills/admin-dashboard/skills.json`
- Create: `service-agent/skills/admin-dashboard/KNOWLEDGE.md` (справочник для Приора)
- Modify: `docker-compose.yml` (env vars для service-agent)
- Modify: `Makefile` (добавить admin-overview target)

- [x] Создать skills.json:
  - id: "admin-dashboard"
  - params: action (enum: overview/instances/set-limit/reset-quota/help), name (optional), limit (optional)
  - timeout: 30
  - env_vars: ["QUOTA_ADMIN_TOKEN", "QUOTA_PROXY_URL", "MONITOR_URL", "BROKER_URL"]
- [x] Создать run.py (Python stdlib, urllib):
  - action "overview": агрегировать quota-report + monitor metrics + broker health + active alerts. В ответ включать подсказки: "Чтобы изменить лимит, вызови admin-dashboard action=set-limit name=X limit=Y"
  - action "instances": список инстансов с квотами, использованием, статусами, подключением к сетям
  - action "set-limit": POST к quota-proxy /quota/set-limit (name, limit). В ответ включать подтверждение и текущее использование
  - action "reset-quota": POST к quota-proxy /quota/reset (name). В ответ включать предупреждение
  - action "help": вернуть полный справочник по API, ключам, сетям, частым ошибкам (читать из KNOWLEDGE.md)
  - Все HTTP-вызовы через urllib.request
- [x] Создать KNOWLEDGE.md — обширная база знаний для Приора:
  Разделы:
  1. Архитектура ключей (полная схема с примерами)
  2. Сети Docker (какой сервис на какой сети, почему)
  3. Частые ошибки и как их чинить:
     - "Instance can't authenticate" -> проверь QUOTA_KEY_* в .env
     - "Broker 403" -> проверь BROKER_KEY_* в .env
     - "Quota exceeded" -> quota.sh report / set-limit
     - "Container unhealthy" -> логи, restart
  4. Пошаговые инструкции для каждой операции
  5. Что НЕЛЬЗЯ делать (danger zone)
  6. Мониторинг: какие метрики смотреть, что нормально, что алерт
- [x] В docker-compose.yml assistant-service: добавить QUOTA_ADMIN_TOKEN, QUOTA_PROXY_URL=http://quota-proxy:9090, MONITOR_URL=http://resource-monitor:9091
- [x] В Makefile: `make admin-overview` — curl к service-agent /v1/run
- [x] Тест: вызвать overview через service-agent API, убедиться что данные корректно агрегированы

### Task 6: qmd — быстрый поиск по markdown файлам (FEATURE)

Утилита для быстрого полнотекстового поиска по всем .md файлам системы: workspace, shared/docs, shared/skills, память.
Реализуется как service-agent skill + shared skill для инстансов.

**Files:**
- Create: `service-agent/skills/qmd/run.py`
- Create: `service-agent/skills/qmd/skills.json`
- Create: `shared/skills/qmd/SKILL.md`
- Modify: `docker-compose.yml` (volume mount для qmd)

- [x] Создать skills.json:
  - id: "qmd"
  - params: query (string, required), scope (enum: "all", "workspace", "shared", "skills", default: "all"), max_results (int, default: 10)
  - timeout: 15
  - env_vars: []
- [x] Создать run.py (Python stdlib, os.walk + re):
  - Рекурсивный обход .md файлов в заданном scope:
    - "workspace": /home/node/.openclaw/workspace/
    - "shared": /shared/docs/ + /shared/skills/
    - "skills": /shared/skills/ only
    - "all": все вышеперечисленное
  - Полнотекстовый поиск (case-insensitive) по содержимому .md файлов
  - Возвращает: [{file, line_number, context (3 строки вокруг), match_count}]
  - Ограничение: max_results (default 10), timeout 10 sec
  - Поддержка regex через re module
- [x] Создать shared/skills/qmd/SKILL.md:
  - Описание: быстрый поиск по документации и базе знаний
  - Примеры: поиск по ключевым словам, regex, фильтр по scope
  - Вызов через service-agent: POST /v1/run с skill_id=qmd
- [x] docker-compose.yml: убедиться что service-agent видит /shared/ volumes
- [x] Тест: найти "quota" по всем md файлам, проверить релевантность результатов

### Task 7: Инфраструктура личных скиллов (FEATURE)

Сейчас все скиллы shared (в /shared/skills/). Нет возможности добавить personal skill конкретному инстансу. Нужна поддержка
workspace/skills/ для персональных навыков.

**Files:**
- Create: `instances/_template/workspace/skills/.gitkeep`
- Modify: `scripts/add-user.sh` (создавать skills/ при создании инстанса)
- Modify: `instances/_template/workspace/TOOLS.md` (документировать personal skills)
- Modify: `shared/docs/common/SKILLS.md` (если существует; иначе создать — документировать personal vs shared)

- [ ] Создать instances/_template/workspace/skills/.gitkeep
- [ ] В add-user.sh: добавить mkdir -p для skills/ в workspace
- [ ] Обновить шаблон TOOLS.md: добавить секцию "Личные скиллы" — инструкция как создать SKILL.md в workspace/skills/
- [ ] Документировать в shared/docs: "Personal vs Shared Skills" — где что, приоритет загрузки
- [ ] Тест: создать тестовый personal skill в workspace/skills/, убедиться что OpenClaw его видит

### Task 8: Финальная проверка и документация (VERIFICATION)

**Files:**
- Modify: `CLAUDE.md` (обновить с новыми компонентами)
- Modify: `.env.example` (добавить новые переменные)

- [ ] Security checks: python3 .github/scripts/ai_security_check.py
- [ ] Shell linting: shellcheck scripts/*.sh
- [ ] make security-check
- [ ] docker compose up -d --build && docker compose ps — все контейнеры healthy
- [ ] E2E тест corp-messenger: отправить сообщение через service-agent, проверить inbox
- [ ] E2E тест broker persistence: отправить сообщение, рестартнуть broker, проверить inbox
- [ ] E2E тест admin-dashboard: вызвать overview и help, проверить полноту данных
- [ ] E2E тест qmd: поиск по md файлам через service-agent
- [ ] Обновить CLAUDE.md: добавить corp-messenger, admin-dashboard, qmd, personal skills в Architecture
- [ ] Обновить .env.example: добавить BROKER_KEY_SERVICE и другие новые vars
- [ ] Переместить этот план в docs/plans/completed/
