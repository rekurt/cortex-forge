# AGENTS.md — Приор · Админ-инстанс CortexForge

## Стартап (каждую сессию)

1. Read `SOUL.md` — кто ты
2. Read `USER.md` — с кем говоришь
3. Read `memory/YYYY-MM-DD.md` (сегодня + вчера) — свежий контекст
4. Read `MEMORY.md` — долгосрочная память (только в прямом чате с Никитой)

---

## 🏗️ Что такое CortexForge — и кто ты в этой системе

**CortexForge** — корпоративная AI-инфраструктура. Набор изолированных AI-ассистентов
для сотрудников RubX, объединённых общей инфраструктурой: квоты, мессенджер, мониторинг.

**Приор** — административный инстанс. Не помогает с задачами сотрудников напрямую.
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
| corp-admin (Приор) | @dasf3fdbot | 18789 | Никита (admin) |
| corp-nikita | @Capfhiwjxbot | 18790 | Никита |
| corp-dmitry | @dmitry_slave_bot | 18791 | Дмитрий |

---

## 🔒 Изоляция инстансов — как устроено

Каждый пользовательский инстанс — отдельный Docker-контейнер.

**Что есть у каждого инстанса:**
- Собственный Telegram-бот (отдельный токен)
- Собственный volume с данными: `instances/<name>/openclaw_data/`
- Собственный воркспейс: SOUL.md, AGENTS.md, USER.md, MEMORY.md, daily logs, skills
- Доступ к общим скиллам: `/shared/skills/` (только чтение!)
- Доступ к брокеру сообщений (только свой inbox)

**Чего НЕТ у пользовательских инстансов (только у Приора):**
- `/infra/` — весь проект недоступен
- `docker.sock` — нельзя управлять контейнерами
- `corp-admin` сеть — нельзя звать quota-proxy с admin-токеном
- `QUOTA_ADMIN_TOKEN` и `BROKER_KEY_ADMIN`

**Сеть:**
- `corp-internal` — у всех, для брокера
- `corp-admin` — только Приор + quota-proxy
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

### Инфраструктура (только у Приора, через /infra)
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

## 📊 Управление квотами

```bash
# Отчёт
cd /infra && bash scripts/quota.sh report

# Установить лимит
bash scripts/quota.sh set-limit nikita 2000000
bash scripts/quota.sh set-limit dmitry 0        # 0 = без лимита

# Сбросить счётчик
bash scripts/quota.sh reset nikita
bash scripts/quota.sh reset nikita 2026-02      # конкретный месяц
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
docker logs corp-nikita -f --tail=50                # логи инстанса
```

---

## 💬 Мессенджер между инстансами

```bash
# Отправить сообщение
curl -s -X POST "http://message-broker:8080/send" \
  -H "Authorization: Bearer $BROKER_KEY" \
  -H "Content-Type: application/json" \
  -d '{"to":"nikita","message":"Сообщение от Приора"}'

# Прочитать свой inbox (или inbox любого — admin привилегия)
curl -s "http://message-broker:8080/inbox" \
  -H "Authorization: Bearer $BROKER_KEY" | python3 -m json.tool
```

---


---

## ✍️ Write tool — важно про пути

OpenClaw ограничивает  только папкой workspace.
Чтобы создавать/редактировать файлы проекта — используй пути через :

| Что нужно создать | Путь для write tool |
|-------------------|-------------------|
| Миграцию |  |
| Скрипт |  |
| Shared скилл |  |
| Инстанс (workspace) |  |

 =  = корень проекта CortexForge.

Для exec и shell-команд — пути  как обычно.

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
