# TOOLS.md — Инфраструктурная шпаргалка Приора

---

## 🗺️ Архитектура CortexForge

```
Интернет
    │
    ▼
[Telegram / мессенджеры]
    │
    ▼
[OpenClaw Gateway] × N  ← по одному на каждого сотрудника
  corp-admin (Приор)    port 18789
  corp-nikita           port 18790
  corp-dmitry           port 18791
    │
    ├──→ [quota-proxy]       port 9090  ← счётчик токенов, единый API-ключ Anthropic
    │         │
    │         └──→ api.anthropic.com
    │
    ├──→ [message-broker]    port 8080  ← межинстансный мессенджер
    │
    ├──→ [resource-monitor]  port 9091  ← CPU/RAM/disk мониторинг
    │
    └──→ [service-agent]     port 8090  ← HTTP API для внешних интеграций
```

## 🖥️ Сервер

- **Хост:** `89.167.99.119` (Ubuntu 24.04)
- **SSH:** `root@89.167.99.119`
- **Проект:** `/opt/cortex-forge/`
- **UFW открыто:** 22, 47022, 80, 443
- **Все internal dashboard ports:** привязаны к `127.0.0.1` — снаружи недоступны

```bash
# Быстрый статус всей системы
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
docker stats --no-stream
df -h /opt/cortex-forge
```

---

## 🐳 Docker сети

| Сеть | Участники | Назначение |
|------|----------|-----------|
| `corp-admin` | Приор, quota-proxy | Управление квотами |
| `corp-internal` | ВСЕ инстансы, broker | Межинстансный мессенджер |
| `corp-egress` | quota-proxy | Форвардинг в api.anthropic.com |
| `corp-outbound` | Приор | Внешние HTTP запросы из Приора |

> Пользовательские инстансы НЕ имеют corp-admin и corp-outbound.
> Это намеренная изоляция — они не могут лезть в инфраструктуру.

---

## 📁 Файловая система — где что хранить

### Workspace Приора (твоё личное пространство)
```
/home/node/.openclaw/workspace/
  SOUL.md              ← кто ты
  USER.md              ← кто с тобой говорит
  AGENTS.md            ← как работаешь
  TOOLS.md             ← этот файл
  IDENTITY.md          ← имя, роль
  MEMORY.md            ← долгосрочная память
  memory/YYYY-MM-DD.md ← daily logs
  HEARTBEAT.md         ← периодические задачи
```

### Инфраструктура (только у Приора)
```
/infra/                   ← весь проект (смонтирован в контейнер)
  docker-compose.yml      ← главный compose
  .env                    ← секреты (не в git)
  instances/
    admin/                ← данные Приора
    nikita/               ← данные инстанса Никиты
    dmitry/               ← данные инстанса Дмитрия
    _template/            ← шаблон нового инстанса
    Dockerfile.user        ← Dockerfile для пользовательских инстансов
  shared/skills/          ← ОБЩИЕ скиллы (read-only для всех!)
  migrations/             ← миграции воркспейсов
  scripts/                ← вспомогательные скрипты
```

### Данные каждого инстанса
```
instances/<name>/openclaw_data/     ← всё данных одного инстанса
  workspace/                        ← файлы конфигурации агента
    SOUL.md, AGENTS.md, USER.md...
    memory/                         ← daily logs
    MEMORY.md                       ← долгосрочная память
    skills/                         ← локальные скиллы этого инстанса
  agents/main/sessions/             ← история сессий (JSONL)
    sessions.json                   ← индекс сессий
    <uuid>.jsonl                    ← история конкретной сессии
  openclaw.json                     ← конфиг OpenClaw (Telegram token, etc.)
  .migrations_applied               ← какие миграции уже накатили
```

### ⚠️ Куда НЕЛЬЗЯ писать
- `/shared/skills/` — смонтировано `:ro` у всех. Скрипты скиллов не могут туда записать ничего.
  State-файлы скиллов → `/home/node/.openclaw/` или `/tmp/`

---

## 🔧 Управление инстансами

### Добавить нового сотрудника
```bash
cd /infra && make add-user NAME=alexey BOT_TOKEN=123:ABC FULL_NAME="Алексей М." TG_ID=123456789
# Создаст: instances/alexey/ со всей структурой
# Добавит в docker-compose.yml
# Запустит контейнер
```

### Остановить / запустить / перезапустить
```bash
cd /infra && docker compose restart corp-nikita
docker compose stop corp-dmitry
docker compose up -d corp-nikita
```

### Логи
```bash
docker logs corp-nikita -f --tail=50
docker logs corp-broker --tail=30
docker logs quota-proxy --tail=30
```

### Обновить образ (для всех user instances)
```bash
cd /infra
docker compose pull          # подтянуть latest
docker compose up -d --build # пересобрать и перезапустить
```

### Очистить сессии инстанса (если бот "завис" в старой личности)
```bash
rm -f /infra/instances/nikita/openclaw_data/agents/main/sessions/*.jsonl
rm -f /infra/instances/nikita/openclaw_data/agents/main/sessions/sessions.json
docker compose restart corp-nikita
```

---

## 📊 Квоты токенов (quota-proxy)

### Скрипт-обёртка
```bash
cd /infra && bash scripts/quota.sh report
bash scripts/quota.sh set-limit nikita 2000000
bash scripts/quota.sh reset nikita
```

### Прямой API
```bash
# Отчёт
curl -s http://quota-proxy:9090/quota/report \
  -H "Authorization: Bearer $QUOTA_ADMIN_TOKEN" | python3 -m json.tool

# Установить лимит
curl -s -X POST http://quota-proxy:9090/quota/set-limit \
  -H "Authorization: Bearer $QUOTA_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"instance":"nikita","limit":2000000}'

# Сбросить счётчик
curl -s -X POST http://quota-proxy:9090/quota/reset \
  -H "Authorization: Bearer $QUOTA_ADMIN_TOKEN" \
  -d '{"instance":"nikita"}'
```

> `QUOTA_ADMIN_TOKEN` — в переменной окружения контейнера (из /infra/.env)

---

## 💬 Мессенджер между ботами (message-broker)

```bash
# Отправить сообщение инстансу nikita
curl -s -X POST "http://message-broker:8080/send" \
  -H "Authorization: Bearer $BROKER_KEY" \
  -H "Content-Type: application/json" \
  -d '{"to":"nikita","message":"Привет от Приора"}'

# Прочитать свой inbox
curl -s "http://message-broker:8080/inbox" \
  -H "Authorization: Bearer $BROKER_KEY" | python3 -m json.tool
```

> У Приора `BROKER_KEY_ADMIN` — это ключ с расширенными правами.
> Обычные инстансы видят только свой inbox. Приор — может видеть всё (admin privilege).

---

## 🔄 Система миграций

```
/infra/migrations/
  001_add_corp_greeting.py   ← добавляет corp-greeting скилл в AGENTS.md
  002_bolder_soul.py         ← обновляет SOUL.md до капуцин-версии
  003_capuchin_soul.py       ← финальная капуцин-душа
  (004_... следующая)
```

**Как работает:**
1. `scripts/migrate-instances.py` — проверяет `.migrations_applied` в каждом инстансе
2. Применяет только новые миграции (идемпотентно)
3. После применения — очищает `agents/main/sessions/` (старые SOUL.md выброшены из памяти)
4. Перезапускает контейнер затронутого инстанса

**Запустить вручную:**
```bash
cd /infra && python3 scripts/migrate-instances.py
```

**Создать новую миграцию:** добавь файл `NNN_описание.py` в `migrations/`
Шаблон — смотри существующие файлы.

---

## 🎭 Общие скиллы (shared/skills)

Смонтированы `:ro` в каждый контейнер по пути `/shared/skills/`.

| Скилл | Описание | Кто использует |
|-------|---------|---------------|
| `corp-greeting` | Генератор случайных приветствий | Все инстансы при старте сессии |
| `corp-messenger` | Отправка сообщений между ботами | Все инстансы |
| `corp-humor` | Пул приматных острот | Все инстансы |
| `compliance-risk` | Проверка контрагентов (ИНН, санкции) | По запросу (требует DaData) |

**Добавить новый скилл:**
1. Создай папку в `/infra/shared/skills/<name>/`
2. Добавь `SKILL.md` — описание для агентов
3. Добавь упоминание в `AGENTS.md` шаблона (`instances/_template/openclaw_data/workspace/AGENTS.md`)
4. При желании создай миграцию чтобы скилл появился в существующих инстансах

**Помни:** скрипты скиллов не могут писать в `/shared/skills/`.
State, кэш, счётчики → `/home/node/.openclaw/workspace/` или `/tmp/`

---

## 🔐 Секреты (где живут)

| Секрет | Где хранится | Как достать |
|--------|-------------|-----------|
| Anthropic API key | `/infra/.env` → `ANTHROPIC_API_KEY` | `$ANTHROPIC_API_KEY` env var |
| Quota admin token | `/infra/.env` → `QUOTA_ADMIN_TOKEN` | `$QUOTA_ADMIN_TOKEN` env var |
| Broker admin key | `/infra/.env` → `BROKER_KEY_ADMIN` | `$BROKER_KEY` env var (в контейнере) |
| Telegram bot tokens | в `instances/<name>/.env` | часть openclaw.json |
| GitHub credentials | `/root/.git-credentials` на хосте | для `git pull` в CI |

**Правило:** секреты не в git, не в ответах пользователям, не в логах.

---

## 📝 Контакты команды RubX

| Человек | Логин | Email | Telegram |
|---------|-------|-------|----------|
| Никита Алдаев | n.aldaev | — | 1934552796 |
| Дмитрий Смирнов | d.smirnov | d.smirnov@rubx.ru | 57096442 |
| Алексей Михайлюк (CPO) | a.mikhailiuk | a.mikhailiuk@rubx.ru | — |
