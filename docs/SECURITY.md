# SECURITY.md — Vulnerability Reporting & Threat Model

## Reporting a Vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

Use **[GitHub Security Advisories](https://github.com/rekurt/corp-assistant/security/advisories/new)** to report privately.

| | SLA |
|---|---|
| Acknowledgement | 72 hours |
| Status update | 7 days |
| Fix target | 30 days for Critical/High |

We will credit you in the release notes unless you prefer to stay anonymous.

### Scope

In-scope: `quota-proxy`, `broker`, `service-agent`, `resource-monitor`, `scripts/`, Docker networking, auth mechanisms.  
Out-of-scope: OpenClaw itself, Anthropic API, third-party GitHub Actions.

---

# Threat Model и Hardening

## Threat Model

**Что защищаем:**
- `ANTHROPIC_API_KEY` — финансовые потери при утечке
- Данные одного инстанса от другого — приватность сотрудников
- Инфраструктуру — от компрометации через скомпрометированный инстанс

**Модель атакующего:**
- Скомпрометированный инстанс (малварь, prompt injection через внешний контент)
- Инсайдер с доступом к Telegram-боту другого сотрудника
- Злоумышленник с доступом к сети сервера

---

## Таблица уязвимостей

| # | Уязвимость | Severity | Статус |
|---|---|---|---|
| V1 | Timing-атака на сравнение токенов | Medium | ✅ Исправлено |
| V2 | Нет rate limiting на API-эндпоинтах | High | ✅ Исправлено |
| V3 | Нет лимита на размер тела запроса | Medium | ✅ Исправлено |
| V4 | SQLite без WAL-mode (deadlock под нагрузкой) | Medium | ✅ Исправлено |
| V5 | quota-proxy порт торчит на localhost хоста | High | ✅ Исправлено |
| V6 | Нет resource limits у контейнеров | Medium | ✅ Исправлено |
| V7 | Нет network segmentation | High | ✅ Исправлено |
| V8 | Нет валидации NAME в add-user.sh | Medium | ✅ Исправлено |
| V9 | Admin монтирует весь /infra (включая .env) | High | ✅ Исправлено |
| V10 | Нет audit log | Medium | ✅ Исправлено |
| V11 | Нет message size limit в broker | Low | ✅ Исправлено |
| V12 | .env permission не проверяются | Low | ✅ Исправлено |
| V13 | Нет security headers в HTTP-ответах | Low | ✅ Исправлено |
| V14 | SIGTERM race в quota-proxy (DB закрывалась до HTTP) | High | ✅ Исправлено |
| V15 | quota-proxy не мог достучаться до api.anthropic.com | Critical | ✅ Исправлено |
| V16 | Существующие тома root:root после перехода на non-root | Medium | ✅ Исправлено |
| V17 | service-agent: subprocess.run без явной whitelist-проверки | High | ✅ Исправлено |

---

## Детали ключевых исправлений

### V1 — Timing attack на токены
```python
# Было (уязвимо к timing attack):
if self.headers.get("Authorization") == f"Bearer {ADMIN_TOKEN}":

# Стало (constant-time):
import hmac
hmac.compare_digest(provided.encode(), expected.encode())
```

### V5 — Exposed port
```yaml
# Было (порт на localhost хоста):
ports:
  - "127.0.0.1:9090:9090"

# Стало: только внутри Docker-сети, порт не пробрасывается
# Доступ к /quota только через admin-контейнер
```

### V7 — Network segmentation
```
Было: одна сеть corp-net (все вместе)

Стало:
  corp-internal  — все инстансы + broker + quota-proxy  (internal: true)
  corp-admin     — admin + quota-proxy + monitor        (internal: true)
  corp-egress    — только quota-proxy                   (не internal → интернет)
  corp-services  — service-agent                        (не internal)
```

### V9 — Admin видит .env с реальным ключом
```yaml
# Было:
volumes:
  - .:/infra  # включает .env с ANTHROPIC_API_KEY

# Стало: монтируем только нужные директории, .env исключён
volumes:
  - ./instances:/infra/instances
  - ./scripts:/infra/scripts:ro
  - ./shared:/infra/shared:ro
```

### V14 — SIGTERM race condition
```python
# Было: _conn.close() вызывался синхронно ДО завершения server.shutdown()
def _shutdown(signum, frame):
    threading.Thread(target=server.shutdown).start()
    _conn.close()   # ← race: in-flight запрос получал ProgrammingError

# Стало: DB закрывается только после полной остановки HTTP
def _shutdown(signum, frame):
    def _do():
        server.shutdown()  # ждёт завершения всех in-flight запросов
        _conn.close()      # только потом закрываем DB
    threading.Thread(target=_do, daemon=True).start()
```

### V15 — quota-proxy без выхода в интернет
```yaml
# Было: все сети internal: true → quota-proxy не мог форвардить в Anthropic
networks:
  corp-internal:
    internal: true
  corp-admin:
    internal: true

# Стало: выделена corp-egress без internal: true только для quota-proxy
networks:
  corp-egress:
    driver: bridge
    # нет internal: true — quota-proxy форвардит в api.anthropic.com
```

### V16 — Volume ownership migration
```python
# proxy.py запускается от root, исправляет /data, дропает привилегии
def _drop_privileges(user="app"):
    if os.getuid() != 0:
        return
    pw = pwd.getpwnam(user)
    # Рекурсивный chown /data (миграция существующих root:root томов)
    for dirpath, dirnames, filenames in os.walk(data_root):
        os.lchown(dirpath, pw.pw_uid, pw.pw_gid)
        ...
    os.setgid(pw.pw_gid)
    os.setuid(pw.pw_uid)
```

### V17 — Skill name injection в service-agent
```python
# Было: whitelist только в HTTP handler, run_skill() не проверял
# Стало: _ALLOWED_SKILLS на уровне модуля + проверка в run_skill() до subprocess

_ALLOWED_SKILLS: set = set()   # заполняется при старте и при /v1/skills

def run_skill(skill_id, caller, params):
    # explicit whitelist check перед subprocess.run()
    if skill_id not in allowed:
        return {"status": "error", "error": "Not in ALLOWED_SKILLS"}
    ...
    subprocess.run(cmd, ...)
```

---

## CI/CD Security Pipeline

GitHub Actions запускает при каждом пуше и PR (`master` + все ветки):

| Job | Инструменты |
|---|---|
| `secrets-scan` | Gitleaks + Semgrep p/secrets |
| `sast-python` | Bandit + Semgrep (python, owasp, command-injection, sql) |
| `ai-security` | Semgrep custom rules + `ai_security_check.py` (8 кастомных проверок) |
| `codeql` | GitHub CodeQL (security-extended + security-and-quality) |
| `docker-lint` | Hadolint + Trivy filesystem |
| `shellcheck` | ShellCheck severity=warning |
| `deps-audit` | pip-audit + Grype |
| `trivy-images` | Trivy scan образов (CRITICAL + HIGH + MEDIUM) |

Кастомные AI-правила (`ai_security_check.py`) проверяют:
- Broker: чтение inbox без авторизации
- Quota proxy: порядок проверки квоты (до upstream-запроса)
- MCP server: отсутствие auth, timing attack на token compare
- Service agent: subprocess без ALLOWED_SKILLS
- Захардкоженные токены (6 паттернов)
- Docker network exposure
- PATH traversal в add-user.sh
- Реальные секреты в .env.example

---

## Остаточные риски (accepted)

| Риск | Причина принятия |
|---|---|
| SQLite не шифрован на диске | Диск сервера должен быть зашифрован на уровне OS |
| Брокер in-memory (сообщения теряются при рестарте) | Приемлемо для некритичных уведомлений; при необходимости заменить `deque` на SQLite |
| HTTP внутри Docker-сети (не TLS) | Docker overlay network изолирована; TLS добавить при выносе на несколько хостов |
| Prompt injection через внешний контент | Ответственность Anthropic safety + настройки системного промпта |

---

## Рекомендации на будущее

1. **Docker secrets** вместо env для `ANTHROPIC_API_KEY`
2. **Encrypt-at-rest** SQLite через SQLCipher или шифрование диска
3. **TLS** между сервисами при выносе на несколько хостов
4. **Ротация ключей** — механизм обновления quota/broker ключей без даунтайма
5. **SIEM** — отправка audit-лога quota-proxy в централизованную систему
6. **Persistent broker** — заменить in-memory deque на SQLite при необходимости надёжной доставки
