"""Add DANGER ZONE, filesystem isolation map, and quota-proxy sections to admin AGENTS.md."""
import pathlib
import re

DESCRIPTION = "add key management, filesystem map, and quota-proxy docs to admin AGENTS.md"

# Sections to inject after "## 🔑 Ключевой принцип (токены)" block
DANGER_ZONE = """\

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
5. Подставляет РЕАЛЬНЫЙ sk-ant-xxx ключ и форвардит в api.anthropic.com
6. Логирует расход токенов в SQLite
```

### Почему инстансы получают ANTHROPIC_API_KEY = quota key

Это ключевой нюанс, который легко перепутать:

1. `openclaw.json.template` содержит `"apiKey": "${ANTHROPIC_API_KEY}"`
2. Docker Compose маппит: `ANTHROPIC_API_KEY=${QUOTA_KEY_USER_1}`
3. OpenClaw видит env-переменную `ANTHROPIC_API_KEY`, подставляет в apiKey
4. Результат: запрос идёт на quota-proxy с quota key, proxy подменяет на реальный

**Это значит:** когда ты видишь `ANTHROPIC_API_KEY` в env инстанса — это **НЕ** реальный ключ Anthropic! Это quota-ключ, который quota-proxy распознаёт и подменяет.
"""

MARKER = "## 🚨 DANGER ZONE"


def apply(workspace: pathlib.Path):
    # Only apply to admin instance
    if workspace.parent.parent.name != "admin":
        # Also check direct workspace path (admin has workspace/ not openclaw_data/workspace/)
        if workspace.parent.name != "admin":
            return

    agents = workspace / "AGENTS.md"
    if not agents.exists():
        return

    content = agents.read_text()

    # Already applied
    if MARKER in content:
        return

    # Insert after the "Ключевой принцип" section's closing ---
    pattern = r"(## 🔑 Ключевой принцип \(токены\).*?---)"
    match = re.search(pattern, content, re.DOTALL)
    if match:
        insert_point = match.end()
        new_content = content[:insert_point] + DANGER_ZONE + content[insert_point:]
        agents.write_text(new_content)
