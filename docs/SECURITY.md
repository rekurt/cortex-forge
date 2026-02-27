# SECURITY.md — Анализ уязвимостей и hardening

## Threat Model

**Что защищаем:**
- Настоящий Anthropic API-ключ (финансовые потери при утечке)
- Данные одного инстанса от другого (приватность сотрудников)
- Инфраструктуру от компрометации через один инстанс

**Атакующие:**
- Скомпрометированный инстанс (малварь, prompt injection через внешний контент)
- Злоумышленник с доступом к сети сервера
- Инсайдер (сотрудник с ботом)

---

## Найденные уязвимости и статус исправления

| # | Уязвимость | Severity | Статус |
|---|---|---|---|
| V1 | Timing-атака на сравнение токенов | Medium | ✅ Исправлено |
| V2 | Нет rate limiting на API эндпоинтах | High | ✅ Исправлено |
| V3 | Нет лимита на размер тела запроса | Medium | ✅ Исправлено |
| V4 | SQLite без WAL-mode (deadlock под нагрузкой) | Medium | ✅ Исправлено |
| V5 | quota-proxy порт торчит на localhost хоста | High | ✅ Исправлено |
| V6 | Нет resource limits у контейнеров | Medium | ✅ Исправлено |
| V7 | Нет network segmentation (все в одной сети) | High | ✅ Исправлено |
| V8 | Нет валидации NAME в add-user.sh | Medium | ✅ Исправлено |
| V9 | Admin монтирует весь /infra (включая .env с ключами) | High | ✅ Исправлено |
| V10 | Нет audit log (невозможно расследовать инцидент) | Medium | ✅ Исправлено |
| V11 | Нет message size limit в broker | Low | ✅ Исправлено |
| V12 | .env permission не проверяется | Low | ✅ Исправлено |
| V13 | Нет security headers в HTTP-ответах | Low | ✅ Исправлено |

---

## Детали уязвимостей

### V1 — Timing attack на токены
```python
# Было (уязвимо):
if self.headers.get("Authorization") == f"Bearer {ADMIN_TOKEN}"

# Стало:
import hmac
hmac.compare_digest(provided, expected)  # constant-time
```

### V2 — Rate limiting
Без ограничений инстанс мог слать тысячи запросов в секунду:
- к `/quota/set-limit` — DoS на admin API
- к `/send` в broker — спам другим инстансам
Добавлен leaky bucket: 60 req/min per IP для admin endpoints, 10 req/min для broker.

### V5 — Exposed port
```yaml
# Было (порт на localhost хоста):
ports:
  - "127.0.0.1:9090:9090"

# Стало: только internal docker network, без проброса
# Доступ к /quota/report только через admin-контейнер
```

### V7 — Network segmentation
```
Было: corp-net (все вместе)

Стало:
  corp-internal  — broker + quota-proxy + инстансы
  corp-admin     — admin + quota-proxy (для управления)
  Инстансы не могут достучаться до admin напрямую
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
  # .env НЕ монтируется
```

---

## Остаточные риски (accepted)

| Риск | Причина принятия |
|---|---|
| SQLite не шифрован на диске | Диск сервера должен быть зашифрован на уровне OS |
| Брокер in-memory (сообщения теряются при рестарте) | Приемлемо для некритичных уведомлений |
| HTTP внутри Docker-сети (не TLS) | Docker overlay network изолирована; TLS можно добавить при необходимости |
| Prompt injection через внешний контент | Ответственность OpenClaw + Anthropic safety |

---

## Рекомендации на будущее

1. **Docker secrets** вместо env для ANTHROPIC_API_KEY
2. **Encrypt-at-rest** SQLite через SQLCipher или шифрование диска
3. **TLS** между сервисами при выносе на несколько хостов
4. **Ротация ключей** — механизм обновления quota-ключей без даунтайма
5. **SIEM** — отправка audit-лога в централизованную систему
