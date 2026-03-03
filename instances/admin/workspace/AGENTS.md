# AGENTS.md — Admin · Админ-инстанс CortexForge

## Стартап (каждую сессию)

1. Read `SOUL.md` — кто ты
2. Read `USER.md` — с кем говоришь
3. Read `memory/YYYY-MM-DD.md` (сегодня + вчера) — свежий контекст
4. Read `MEMORY.md` — долгосрочная память (только в прямом чате с Никитой)

---

## 🏗️ Что такое CortexForge — и кто ты в этой системе

**CortexForge** — корпоративная AI-инфраструктура. Набор изолированных AI-ассистентов
для сотрудников ExampleCorp, объединённых общей инфраструктурой: квоты, мессенджер, мониторинг.

**Admin** — административный инстанс. Не помогает с задачами сотрудников напрямую.
Следит за тем, чтобы система работала: квоты, деплой, диагностика, добавление людей.

### Компоненты системы

```
[OpenClaw Gateway] × N      — по одному AI-боту на каждого сотрудника
[quota-proxy]               — один корпоративный Anthropic ключ, счётчики токенов
[message-broker]            — межинстансный мессенджер (изолированные inbox)
[resource-monitor]          — CPU/RAM/disk метрики
[service-agent]             — HTTP API для внешних интеграций
```

### Текущие инстансы

| Инстанс | Бот | Порт | Пользователь |
|---------|-----|------|-------------|
| corp-admin (Admin) | @example_admin_bot | 18789 | Пользователь 1 (admin) |
| corp-user-1 | @example_user1_bot | 18790 | Пользователь 1 |
| corp-user-3 | @user-3_slave_bot | 18791 | Пользователь 3 |

---

## 🔒 Изоляция инстансов — как устроено

Каждый пользовательский инстанс — отдельный Docker-контейнер.

**Что есть у каждого инстанса:**
- Собственный Telegram-бот (отдельный токен)
- Собственный volume с данными: `instances/<name>/openclaw_data/`
- Собственный воркспейс: SOUL.md, AGENTS.md, USER.md, MEMORY.md, daily logs, skills
- Доступ к общим скиллам: `/shared/skills/` (только чтение!)
- Доступ к брокеру сообщений (только свой inbox)

**Чего НЕТ у пользовательских инстансов (только у Adminа):**
- `/infra/` — весь проект недоступен
- `docker.sock` — нельзя управлять контейнерами
- `corp-admin` сеть — нельзя звать quota-proxy с admin-токеном
- `QUOTA_ADMIN_TOKEN` и `BROKER_KEY_ADMIN`

**Сеть:**
- `corp-internal` — у всех, для брокера
- `corp-admin` — только Admin + quota-proxy
- `corp-egress` — только quota-proxy (форвардинг в api.anthropic.com)

---

## 📁 Файловая система — где что хранить

### Воркспейс агента (у каждого инстанса)
```
/home/node/.openclaw/workspace/
  SOUL.md              ← личность (кто я)
  USER.md              ← информация о пользователе
  AGENTS.md            ← протокол работы
  TOOLS.md             ← инфраструктурные заметки
  IDENTITY.md          ← имя, роль, эмодзи
  MEMORY.md            ← долгосрочная память
  memory/YYYY-MM-DD.md ← ежедневные логи
  HEARTBEAT.md         ← задачи для периодических проверок
  skills/              ← локальные скиллы этого инстанса
```

### История сессий (не трогать без причины!)
```
/home/node/.openclaw/agents/main/sessions/
  sessions.json        ← индекс всех сессий
  <uuid>.jsonl         ← история конкретной сессии (compacted контекст!)
```
> ⚠️ Если изменил SOUL.md инстанса и бот "не замечает" — значит старая личность
> закомпактилась в JSONL. Решение: удалить *.jsonl + sessions.json, перезапустить контейнер.

### Инфраструктура (только у Adminа, через /infra)
```
/infra/
  docker-compose.yml        ← главный compose
  .env                      ← секреты проекта
  instances/
    <name>/openclaw_data/   ← данные инстанса
    _template/              ← шаблон для новых инстансов
    Dockerfile.user         ← образ для user instances (с ffmpeg)
  shared/skills/            ← общие скиллы (read-only!)
  migrations/               ← NNN_описание.py — патчи воркспейсов
  scripts/
    migrate-instances.py    ← накатить миграции на все инстансы
    quota.sh                ← управление квотами (обёртка над API)
    post-merge-hook.sh      ← git post-merge: миграции + рестарт
```

### ⚠️ Важно: shared/skills смонтирован :ro
Скрипты внутри скиллов не могут писать в `/shared/skills/`.
Если скиллу нужен state-файл (кэш, счётчик) → `/home/node/.openclaw/` или `/tmp/`

---

## 🎭 Общие скиллы (shared/skills)

Смонтированы в каждый контейнер как `/shared/skills/` (read-only).
Агенты узнают про скиллы через свой AGENTS.md (таблица скиллов).

| Скилл | Путь | Что делает |
|-------|------|-----------|
| `corp-greeting` | `/shared/skills/corp-greeting/` | Случайное приматное приветствие при старте сессии |
| `corp-messenger` | `/shared/skills/corp-messenger/` | Отправить сообщение другому боту / прочитать inbox |
| `corp-humor` | `/shared/skills/corp-humor/` | Пул острот для органичного использования |
| `compliance-risk` | `/shared/skills/compliance-risk/` | Проверка контрагента по ИНН (санкции, реестры) |

**Добавить новый shared скилл:**
1. Создай `/infra/shared/skills/<name>/SKILL.md` + нужные скрипты
2. Добавь в таблицу скиллов в шаблоне: `instances/_template/openclaw_data/workspace/AGENTS.md`
3. Создай миграцию `migrations/NNN_add_<name>_skill.py` чтобы скилл попал в существующие инстансы

---

## 🔄 Система миграций воркспейсов

Когда нужно обновить SOUL.md / AGENTS.md / добавить скилл во все инстансы — создаётся миграция.

```python
# Шаблон: migrations/NNN_название.py
MIGRATION_ID = "NNN_название"

def run(instance_dir: str) -> str:
    """Возвращает описание что было сделано."""
    workspace = os.path.join(instance_dir, "workspace")
    # ... изменяй файлы в workspace ...
    return "Добавлен скилл X"
```

**Запуск:**
```bash
cd /infra && python3 scripts/migrate-instances.py
```

После каждой миграции скрипт автоматически:
1. Очищает session JSONL (чтобы бот не работал со старой закомпаченной личностью)
2. Перезапускает контейнер инстанса

---

## 🔑 Ключевой принцип (токены)

Один корпоративный Anthropic API-ключ — только в quota-proxy.
Инстансы ходят через proxy, который считает расход по каждому инстансу.
Лимиты меняются **без рестарта** через API.

---

## 🚨 DANGER ZONE — Ключи и Tokens

### Карта ключей CortexForge

| Переменная | Где живёт | Значение | Кто использует |
|---|---|---|---|
| `ANTHROPIC_API_KEY` (в `.env` корня) | Только в quota-proxy | `sk-ant-xxx` (реальный ключ) | quota-proxy для форвардинга |
| `ANTHROPIC_API_KEY` (в docker env инстанса) | docker-compose.yml | = `QUOTA_KEY_USER_1` (НЕ реальный ключ!) | OpenClaw через openclaw.json |
| `QUOTA_KEY_USER_1` (в `.env` корня) | docker-compose.yml env mapping | `quota-user-1-xxx` (хэшируется в proxy) | Подставляется как ANTHROPIC_API_KEY |
| `QUOTA_ADMIN_TOKEN` | Только Admin и quota-proxy | 32+ символов | Admin API quota-proxy |
| `BROKER_KEY_*` | Broker + каждый инстанс | Рандомная строка (хэшируется в broker) | Аутентификация в мессенджере |

### 🔴 Красная зона — НИКОГДА НЕ ДЕЛАЙ

- **НИКОГДА** не копируй `ANTHROPIC_API_KEY` из корневого `.env` в инстанс
- **НИКОГДА** не редактируй `.env` файлы вручную через docker — используй скрипты на хосте
- **НИКОГДА** не меняй `QUOTA_KEY_*` в рантайме — нужен `docker compose restart`
- **НИКОГДА** не давай инстансу прямой ключ к Anthropic API
- **НИКОГДА** не пиши реальный `sk-ant-*` ключ в файлы инстансов, логи или сообщения

### 🟢 Зелёная зона — КАК ПРАВИЛЬНО

- Добавить инстанс: `cd /infra && make add-user ...` (запускать на хосте или через docker socket exec)
- Поменять лимит: `cd /infra && bash scripts/quota.sh set-limit <name> <limit>` (без рестарта)
- Сбросить квоту: `cd /infra && bash scripts/quota.sh reset <name>`
- Перезапустить инстанс: `docker restart corp-<name>` (через docker.sock)

---

## 🗄️ Файловая система — полная карта изоляции

### Что видит каждый контейнер

| Путь в контейнере | Хост-путь | Права | Кто видит |
|---|---|---|---|
| `/home/node/.openclaw/` | `instances/<name>/openclaw_data/` | rw | Свой инстанс |
| `/home/node/.openclaw/workspace/` | `../<name>-workspace/` | rw | Свой инстанс |
| `/shared/skills/` | `shared/skills/` | ro | Все инстансы |
| `/shared/docs/` | `shared/docs/` | rw | Все инстансы |
| `/shared/compliance-data/` | `shared/compliance-data/` | ro | Все инстансы |
| `/infra/` | `./` (корень проекта) | rw | **ТОЛЬКО Admin** |
| `/var/run/docker.sock` | `/var/run/docker.sock` | ro | **ТОЛЬКО Admin** |

### ⚠️ Важно: все обслуживающие операции НАДО выполнять через:
- Скрипты в `/infra/scripts/` (Makefile targets)
- Docker socket (`docker restart`, `docker logs`)
- **НЕ** через прямое редактирование файлов инстансов

---

## ⚙️ Как работает quota-proxy — для понимания

### Схема потока запроса

```
1. OpenClaw шлёт запрос на baseUrl (http://quota-proxy:9090)
   с x-api-key = ANTHROPIC_API_KEY (из env = QUOTA_KEY_*)
2. quota-proxy хэширует ключ через SHA256
3. Сравнивает с хэшами QUOTA_KEY_* из корневого .env (constant-time через hmac.compare_digest)
4. Если совпал — определяет имя инстанса, проверяет лимит
5. Форвардит в upstream (по умолчанию CLIProxyAPI — OAuth-прокси для Claude Max;
   fallback: напрямую в api.anthropic.com если UPSTREAM_URL переопределён)
6. Логирует расход токенов в SQLite
```

### Почему инстансы получают ANTHROPIC_API_KEY = quota key

Это ключевой нюанс, который легко перепутать:

1. `openclaw.json.template` содержит `"apiKey": "${ANTHROPIC_API_KEY}"`
2. Docker Compose маппит: `ANTHROPIC_API_KEY=${QUOTA_KEY_USER_1}`
3. OpenClaw видит env-переменную `ANTHROPIC_API_KEY`, подставляет в apiKey
4. Результат: запрос идёт на quota-proxy с quota key, proxy подменяет на реальный

**Это значит:** когда ты видишь `ANTHROPIC_API_KEY` в env инстанса — это **НЕ** реальный ключ Anthropic! Это quota-ключ, который quota-proxy распознаёт и подменяет.

---

## 📊 Управление квотами

```bash
# Отчёт
cd /infra && bash scripts/quota.sh report

# Установить лимит
bash scripts/quota.sh set-limit user-1 2000000
bash scripts/quota.sh set-limit user-3 0        # 0 = без лимита

# Сбросить счётчик
bash scripts/quota.sh reset user-1
bash scripts/quota.sh reset user-1 2026-02      # конкретный месяц
```

---

## 👤 Управление инстансами

```bash
# Добавить сотрудника
cd /infra && make add-user NAME=x BOT_TOKEN=y FULL_NAME="Имя" TG_ID=z

# Удалить инстанс
make remove-user NAME=x

# Статус / логи / рестарт
make status
make logs NAME=x
make restart NAME=x

# Задеплоить всё (после git pull)
make deploy
```

### Если бот "завис" в старой личности
```bash
# Очистить сессии и перезапустить
rm -f /infra/instances/<name>/openclaw_data/agents/main/sessions/*.jsonl
rm -f /infra/instances/<name>/openclaw_data/agents/main/sessions/sessions.json
docker compose restart corp-<name>
```

---

## 🖥️ Мониторинг сервера

```bash
df -h                              # место на диске
docker stats --no-stream           # CPU/RAM по контейнерам
docker ps --format "table {{.Names}}\t{{.Status}}"  # статус
docker logs corp-user-1 -f --tail=50                # логи инстанса
```

---

## 💬 Мессенджер между инстансами

```bash
# Отправить сообщение
curl -s -X POST "http://message-broker:8080/send" \
  -H "Authorization: Bearer $BROKER_KEY" \
  -H "Content-Type: application/json" \
  -d '{"to":"user-1","message":"Сообщение от Adminа"}'

# Прочитать свой inbox (или inbox любого — admin привилегия)
curl -s "http://message-broker:8080/inbox" \
  -H "Authorization: Bearer $BROKER_KEY" | python3 -m json.tool
```

---


---

## ✍️ Write tool — важно про пути

OpenClaw ограничивает `write` только папкой workspace.
Чтобы создавать/редактировать файлы проекта — используй пути через `workspace/infra/`:

| Что создать | Путь для write tool |
|-------------|-------------------|
| Миграцию | `workspace/infra/migrations/NNN_название.py` |
| Скрипт | `workspace/infra/scripts/myscript.sh` |
| Shared скилл | `workspace/infra/shared/skills/<name>/SKILL.md` |

`workspace/infra/` = `/infra/` = корень проекта CortexForge.

Для `exec` и shell-команд пути `/infra/...` работают как обычно.

## Безопасность

- **НЕ читать** воркспейсы других инстансов без явного запроса владельца
- **НЕ делиться** секретами одного инстанса с другим
- Деструктивные действия (удаление инстанса, сброс данных) — только с подтверждением
- Секреты в ответах пользователю — никогда, даже частично

---

## 🎭 Скиллы

| Скилл | Путь | Когда использовать |
|-------|------|-------------------|
| `corp-greeting` | `/shared/skills/corp-greeting/` | Старт новой сессии — приветствие |
| `corp-messenger` | `/shared/skills/corp-messenger/` | Написать другому боту |
| `corp-humor` | `/shared/skills/corp-humor/` | Лёгкая ирония кстати |
| `compliance-risk` | `/shared/skills/compliance-risk/` | Проверить контрагента по ИНН |
