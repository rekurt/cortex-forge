# TODO — CortexForge Admin Workspace Refactoring

Дата: 2026-03-03
Статус: планирование

---

## Группа A: Docker Infrastructure

### A1. [п.1] Монтировать весь проект в /infra/ для admin (rw)

- [x] **Файл:** `docker-compose.yml` → секция `assistant-admin.volumes`
- [x] Заменить точечные mounts (`./instances`, `./scripts:ro`, `./shared:ro`) на один `./:/infra/`
- [x] Admin уже получает `ANTHROPIC_API_KEY` через `environment:` — доступ к `.env` через FS не добавляет нового риска
- [x] Обновить доку (AGENTS.md, TOOLS.md)

### A2. [п.8, п.22] shared/skills → rw для всех

- [x] **Файл:** `docker-compose.yml`
- [x] Убрать `:ro` с `./shared/skills` у admin и всех user instances
- [x] service-agent оставить `:ro` (он не должен модифицировать скиллы)
- [x] Обновить доку: AGENTS.md стр. 48 ("только чтение!"), стр. 98, стр. 106-108, стр. 114, стр. 202

### A3. [п.10, п.24] Разделить docker-compose на base + override

- [x] Вынести `assistant-nikita`, `assistant-vasily`, `assistant-dmitry` из `docker-compose.yml` в `docker-compose.override.yml`
- [x] Base файл: инфраструктура (cliproxyapi, quota-proxy, broker, monitor, service-agent, admin)
- [x] Override: пользовательские инстансы (создаются через `add-user.sh`, gitignored)
- [x] Обновить `.gitignore` — `docker-compose.override.yml` уже там
- [x] Обновить доку

### A4. [п.35] Вынести admin workspace вне репо

- [x] Сейчас: `./instances/admin/workspace` (внутри репо, трекается git)
- [x] Цель: `../admin-workspace` (как user instances)
- [x] **Файл:** `docker-compose.yml` → `assistant-admin.volumes`
- [x] Изменить mount: `../admin-workspace:/home/node/.openclaw/workspace`
- [x] Скопировать текущий workspace в `../admin-workspace/`
- [x] Обновить `.gitignore` — убрать `!instances/admin/workspace/`
- [x] Обновить доку: AGENTS.md filesystem map стр. 200-201

---

## Группа B: Broker — Admin Privileges

### B1. [п.9] Добавить admin-привилегию в broker

- [x] **Файл:** `broker/broker.py`
- [x] Логика: если `_auth()` возвращает `"admin"`, разрешить `GET /inbox?for=<name>` — чтение inbox любого инстанса
- [x] Добавить query parameter `for` в `do_GET` для `/inbox`
- [x] Оставить rate limit для admin, но не ограничивать inbox чтение
- [x] Добавить `GET /inbox/all` — список всех inbox (counts) — или использовать `/health` для этого
- [x] Обновить доку: AGENTS.md стр. 308

---

## Группа C: Git / Submodules

### C1. [п.7, п.34] Добавить compliance-risk как git submodule

- [x] `git submodule add https://github.com/rekurt/compliance-risk shared/skills/compliance-risk`
- [x] Это заполнит пустую директорию `shared/skills/compliance-risk/` содержимым репо
- [x] Обновить `.gitmodules`
- [x] Обновить доку: shared skills таблица в AGENTS.md и TOOLS.md

---

## Группа D: AGENTS.md — фиксы документации

### D1. [п.2] Убрать секцию "Write tool — важно про пути"

- [x] Стр. 317-331 — вся секция ложная (`workspace/infra/` != `/infra/`)
- [x] После A1 (весь проект в /infra/) exec-команды будут работать через `/infra/...` напрямую
- [x] Заменить на корректное описание: write tool = workspace, exec = /infra/

### D2. [п.3] Исправить шаблон миграции

- [x] Стр. 135-144: заменить `MIGRATION_ID` → `DESCRIPTION`, `run(instance_dir)` → `apply(workspace: pathlib.Path)`

### D3. [п.4] Добавить CLIProxyAPI в архитектуру

- [x] Стр. 22-28: добавить `[cliproxyapi]` в диаграмму компонентов
- [x] Описать: OAuth-прокси для Claude Max, порт 8317, контейнер `corp-cliproxyapi`

### D4. [п.5] Добавить upstream modes quota-proxy

- [x] После стр. 227: описать 3 режима (CLIProxyAPI, OAuth, Standard)
- [x] Упомянуть `UPSTREAM_URL`, `UPSTREAM_API_KEY`, `CLIPROXY_API_KEY`

### D5. [п.6] Добавить rate limits

- [x] В секцию quota-proxy: 300 req/min на инстанс, 60 req/min на admin
- [x] В секцию broker: 10 msg/min на инстанс

### D6. [п.7] Обновить таблицу shared skills

- [x] Стр. 117-122 и 342-348: добавить `capuchin-mcp`, `corp-docs`, `doc-translator`, `qmd`, `yandex-oauth`
- [x] Обновить `compliance-risk` после подключения submodule (C1)

### D7. [п.9] Обновить broker docs — admin привилегия

- [x] Стр. 308: после B1 обновить описание inbox — admin может читать inbox любого через `?for=<name>` (выполнено в B1, стр. 356-362)

### D8. [п.10] Обновить таблицу инстансов

- [x] Стр. 32-36: убрать ложные порты для user instances, добавить vasily, пометить что user instances в override

### D9. [п.11] Создать memory/ и MEMORY.md в admin workspace

- [x] `mkdir -p instances/admin/workspace/memory` (или `../admin-workspace/memory` после A4)
- [x] Создать `MEMORY.md` (базовый шаблон)
- [x] Обновить стартап-протокол стр. 3-8 — убедиться что пути корректны

### D10. [п.12] Исправить workspace host path для admin

- [x] Стр. 200-201: admin workspace → `../admin-workspace/` (после A4) — выполнено в рамках A4, таблица AGENTS.md стр. 224 уже использует шаблон `../<name>-workspace/`

### D11. [п.13] Исправить shared/compliance-data права

- [x] Стр. 204: admin = rw, user instances = ro (отразить реальность docker-compose)

### D12. [п.14] Добавить resource-monitor API

- [x] Новая секция: `GET /metrics`, `GET /metrics/<name>`, `GET /alerts/active`
- [x] Auth: `MONITOR_ADMIN_TOKEN` (Bearer)
- [x] Admin имеет доступ через `corp-admin` сеть

### D13. [п.15] Добавить service-agent API

- [x] Новая секция: `POST /v1/run`, `GET /v1/skills`, `GET /v1/health`, `GET /v1/usage`
- [x] Auth: `SERVICE_API_KEY` (Bearer)

### D14. [п.16] Расширить quota-proxy API docs

- [x] Добавить: `GET /quota/health` (публичный), `?month=YYYY-MM`, формат ответов
- [x] Instance auth: и `x-api-key`, и `Authorization: Bearer`

### D15. [п.17] Добавить формат ответов broker API

- [x] `/inbox` → `{"inbox": [...], "count": N}`
- [x] `/send` → `{"ok": true, "from": "...", "to": "..."}`
- [x] `/health` → `{"status": "ok", "instances": [...], "message_counts": {...}}`

---

## Группа E: TOOLS.md — фиксы

### E1. [п.19] Добавить CLIProxyAPI в таблицу сервисов

- [x] Добавить строку: `cliproxyapi | corp-cliproxyapi | http://cliproxyapi:8317 | — | OAuth-прокси для Claude Max`

### E2. [п.20] Сети Docker — верифицировать

- [x] Верифицировано: corp-egress включает cliproxyapi, corp-services есть, все 5 сетей корректны
- [x] Исправлено: corp-internal "Все контейнеры" → "Все кроме cliproxyapi" (cliproxyapi только в corp-egress)

### E3. [п.21] Обновить таблицу shared skills

- Дублируется с D6. Добавить недостающие скиллы.

### E4. [п.23] Миграции

- TOOLS.md упрощён, миграции убраны. Не требуется.

### E5. [п.25] /infra/ пути

- Исправится автоматически после A1. Верифицировать.

### E6. [п.26] Container names в примерах

- Проверить примеры команд — использовать `corp-quota` вместо `quota-proxy` для `docker logs`

### E7. [п.27] Дубликаты

- TOOLS.md уже упрощён. Проверить AGENTS.md на повторения.

### E8. [п.28] Добавить новые env vars

- `UPSTREAM_URL`, `UPSTREAM_API_KEY`, `CLIPROXY_API_KEY`, `MONITOR_ADMIN_TOKEN`, `BROKER_KEY_MONITOR`

### E9. [п.29] Quota-proxy API

- Дублируется с D14. Убедиться что TOOLS.md ссылается на AGENTS.md или содержит консистентную информацию.

### E10. [п.30] SOUL.md — неполный список файлов при старте

- Стр. 48: добавить `IDENTITY.md`, `TOOLS.md`, `HEARTBEAT.md` в список

---

## Группа F: SOUL.md — Верховный Капуцин

### F1. [п.32] Переписать SOUL.md для admin — Приор как вожак племени

- Текущий SOUL.md описывает "послушную обезьянку"
- Нужно: верховный капуцин, альфа-самец, управляющий племенем (стаей ботов)
- Сохранить: прямой тон, workaround-мышление, отсутствие AI-формализмов
- Добавить: авторитет вожака, ответственность за племя, стратегическое мышление
- НЕ трогать `_template/workspace/SOUL.md` — он для рядовых капуцинов

---

## Группа G: USER.md

### G1. [п.32 implied] Заполнить USER.md для admin

- Имя: Никита
- Роль: admin / владелец инфраструктуры
- Таймзона: определить

---

## Группа H: Template

### H1. [п.11] Обновить template

- Проверить `instances/_template/workspace/AGENTS.md` — добавить все актуальные shared skills
- Проверить `instances/_template/workspace/SOUL.md` — уже актуален
- Проверить `instances/_template/workspace/TOOLS.md` — обновить shared skills список
- Убедиться что `memory/` и `MEMORY.md` создаются (`add-user.sh` уже делает `mkdir -p memory`)

---

## Группа I: add-user.sh / remove-user.sh фиксы

### I1. [п.18] Убрать мёртвую копию workspace в openclaw_data

- `add-user.sh` стр. 49-50: убрать `mkdir -p "$TARGET/openclaw_data/workspace/memory"` и `mkdir -p "$TARGET/openclaw_data/workspace/skills"`
- Стр. 73-74: убрать копирование шаблона в `$TARGET/openclaw_data/workspace/`
- Workspace создаётся только в `../${NAME}-workspace/`

### I2. [п.18] Исправить post-creation instructions

- Стр. 202: `nano instances/$NAME/workspace/SOUL.md` → `nano ../${NAME}-workspace/SOUL.md`

### I3. [п.18] remove-user.sh: исправить архивирование

- Стр. 28: `tar -czf "$ARCHIVE" "$TARGET/workspace"` → `tar -czf "$ARCHIVE" "../${NAME}-workspace"`

### I4. [п.18] remove-user.sh: удалять external workspace

- Добавить после стр. 32: `rm -rf "../${NAME}-workspace"` (с подтверждением)

### I5. [п.18] remove-user.sh: guard для отсутствующего override

- Стр. 59: `open('docker-compose.override.yml')` — добавить проверку файла перед открытием

### I6. [п.36] Обновить документацию о Dockerfile.user

- AGENTS.md / TOOLS.md: описать что user instances строятся из `Dockerfile.user` (через override), а admin использует `ghcr.io/openclaw/openclaw:latest`

---

## Порядок выполнения (зависимости)

```
C1 (submodule)          ─── параллельно
B1 (broker admin)       ─── параллельно
F1 (SOUL.md)            ─── параллельно
G1 (USER.md)            ─── параллельно

A1 (mount /infra/ rw)   ──┐
A2 (skills rw)           ──┤
A3 (split compose)       ──┼── инфра-блок (последовательно)
A4 (admin workspace out) ──┘

I1-I5 (scripts fix)     ─── после A3

D1-D15 (AGENTS.md)      ──┐
E1-E10 (TOOLS.md)        ──┼── дока (после всех инфра-изменений)
H1 (template)            ──┘

D9 (memory/)             ─── можно параллельно с чем угодно
```

---

## Принятые решения

1. **п.1 mount /infra/**: монтируем `./:/infra/` rw целиком, включая `.env`. Admin и так имеет `ANTHROPIC_API_KEY` через env.
2. **п.9 broker admin**: реализуем через query param `GET /inbox?for=<name>` — admin может указать чей inbox читать.
3. **п.10 + п.24**: nikita/vasily/dmitry переезжают из `docker-compose.yml` в `docker-compose.override.yml`.
4. **п.35**: admin workspace переезжает в `../admin-workspace/`.
5. **п.32**: Приор = альфа-капуцин, вожак стаи. Не "послушная обезьянка", а лидер.