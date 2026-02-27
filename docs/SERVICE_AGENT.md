# Service Agent — HTTP API для внутренних сервисов

Service Agent — реплицируемый HTTP-сервер, принимающий задачи от внутренних
бэкенд-сервисов и выполняющий скиллы как субпроцессы. Python stdlib only.

## Архитектура

```
Internal Backend Service
        │
        │  POST /v1/run
        │  Authorization: Bearer SERVICE_API_KEY
        ▼
  Service Agent (corp-service)        порт 8090
        │
        │  subprocess.run(skills/compliance/run.py)
        │  params → stdin (JSON), result ← stdout (JSON)
        ▼
  enrich.py / другие скиллы
```

## API

### POST /v1/run

Выполнить скилл. Требует авторизации.

**Запрос:**
```json
{
  "skill":  "compliance",
  "caller": "backend-kyc-service",
  "params": {
    "inn":  "7707083893",
    "mode": "full"
  }
}
```

**Успешный ответ (200):**
```json
{
  "status":      "ok",
  "skill":       "compliance",
  "duration_ms": 8234,
  "result": {
    "...": "enrich.py JSON output"
  }
}
```

**Ошибка (500):**
```json
{
  "status":      "error",
  "skill":       "compliance",
  "error":       "описание ошибки",
  "duration_ms": 123
}
```

### GET /v1/skills

Список доступных скиллов с описанием параметров. Требует авторизации.

```json
{
  "skills": [
    {
      "id":          "compliance",
      "name":        "Compliance Risk Check",
      "description": "Проверка контрагента по ИНН (RU/BY/KZ)",
      "params": {
        "inn":  { "type": "string",  "required": true },
        "mode": { "type": "string",  "required": false, "default": "full" }
      },
      "timeout": 150
    }
  ],
  "count": 1
}
```

### GET /v1/health

Healthcheck без авторизации. Используется Docker для `healthcheck`.

```json
{
  "status": "ok",
  "skills_dir": "/app/skills",
  "max_concurrent": 5
}
```

### GET /v1/usage

Статистика вызовов по скиллам. Требует авторизации.

```json
{
  "by_skill": [
    {
      "skill":              "compliance",
      "total_calls":        42,
      "successful":         40,
      "avg_duration_ms":    7821.3,
      "total_output_bytes": 183420,
      "last_called":        "2026-02-27T16:00:00+00:00"
    }
  ]
}
```

## Параллельность и лимиты

| Параметр              | Default | Env                    |
|-----------------------|---------|------------------------|
| Параллельных задач    | 5       | `MAX_CONCURRENT_TASKS` |
| Таймаут скилла        | 120 s   | `SKILL_TIMEOUT`        |
| CPU (docker limit)    | 2.0     | —                      |
| RAM (docker limit)    | 1 G     | —                      |

При превышении `MAX_CONCURRENT_TASKS` возвращается 500 с `"Too many concurrent tasks"`.

## Compliance skill и enrich.py

`enrich.py` намеренно **не хранится в репозитории** — он большой и обновляется
независимо от image. Монтируется через volume:

```yaml
volumes:
  - ${ENRICH_PY_PATH:-./service-agent/skills/compliance/enrich_placeholder.py}:/app/skills/compliance/enrich.py:ro
```

Настройка в `.env`:
```
ENRICH_PY_PATH=/home/user/.openclaw/workspace/skills/compliance-risk/scripts/enrich.py
```

## Репликация service-инстансов

```bash
# Сгенерировать конфиг второго инстанса на порту 8091
make add-service NAME=svc-kyc PORT=8091 SKILLS=compliance,kyc
```

Скрипт добавит ключ в `.env` и выведет YAML-блок для вставки в `docker-compose.yml`.

## Добавление нового скилла

1. Создай `service-agent/skills/{skill-name}/`
2. Добавь `run.py` или `run.sh`:
   - читает JSON-параметры из **stdin**
   - выводит JSON-результат в **stdout**
   - при ошибке выходит с `sys.exit(1)` и пишет JSON с `"error"` на stdout
3. Добавь `skills.json` (манифест — см. compliance/skills.json для примера)
4. Пересобери образ: `docker compose build assistant-service`

### Минимальный `run.py`:
```python
import sys, json

params = json.load(sys.stdin)
# ... do work ...
print(json.dumps({"result": "done", "input": params}))
```

## Безопасность

- Порт `8090` пробрасывается только на `127.0.0.1` — снаружи недоступен
- `no-new-privileges:true`
- Skills монтируются `:ro` (read-only)
- `enrich.py` монтируется `:ro`
- Все вызовы логируются в SQLite (`/data/usage.db`)
- **Whitelist скиллов:** `_ALLOWED_SKILLS` (module-level `set`) заполняется при старте из `SKILLS_DIR`. `run_skill()` проверяет `skill_id not in allowed` **до** `subprocess.run()` — даже при прямом вызове в обход HTTP handler. Обновляется при запросе `GET /v1/skills`.
