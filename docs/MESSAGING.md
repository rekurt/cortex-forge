# MESSAGING.md — Межинстансный мессенджер

## Принцип работы

```
user-1-бот                 message-broker              user-2-бот
    │                           │                           │
    │  POST /send               │                           │
    │  {to:"user-2",            │                           │
    │   message:"привет"}       │                           │
    ├──────────────────────────►│                           │
    │                           │  кладёт в inbox[user-2]   │
    │  200 OK                   │                           │
    │◄──────────────────────────┤                           │
    │                           │                           │
    │                           │   GET /inbox              │
    │                           │◄──────────────────────────┤
    │                           │                           │
    │                           │  [{from:"user-1",...}]    │
    │                           ├──────────────────────────►│
```

---

## API брокера

Все эндпоинты кроме `/health` требуют авторизации: `Authorization: Bearer $BROKER_KEY`

### POST /send — отправить сообщение

```bash
curl -X POST http://message-broker:8080/send \
  -H "Authorization: Bearer $BROKER_KEY" \
  -H "Content-Type: application/json" \
  -d '{"to":"user-2","message":"Привет от Никиты: нужен отчёт по спринту к пятнице"}'
# → {"status":"ok"}
```

### GET /inbox — прочитать входящие

Возвращает все непрочитанные сообщения для текущего инстанса (определяется по ключу).

```bash
curl http://message-broker:8080/inbox \
  -H "Authorization: Bearer $BROKER_KEY"
# → [{"from":"user-1","message":"Привет от Никиты: ...","ts":1740672000}]
```

### DELETE /inbox — очистить inbox

После обработки сообщений очищает очередь.

```bash
curl -X DELETE http://message-broker:8080/inbox \
  -H "Authorization: Bearer $BROKER_KEY"
# → {"status":"ok","deleted":3}
```

### GET /health — healthcheck (без авторизации)

```bash
curl http://message-broker:8080/health
# → {"status":"ok"}
```

---

## Безопасность

| Угроза | Защита |
|---|---|
| Инстанс A читает inbox B | Нельзя — брокер определяет владельца по API-ключу, не по параметрам запроса |
| Инстанс A отправляет от имени B | Нельзя — sender определяется по ключу, не по полю `from` в теле |
| Внешний запрос к брокеру | Нельзя — порт не пробрасывается наружу, только `corp-internal` сеть |
| Перехват сообщений | Docker-сеть `internal: true` изолирована; при необходимости добавить TLS |
| Переполнение inbox | Message size limit + max inbox depth настроены в broker.py |

---

## Ограничения текущей версии

- **In-memory** — сообщения не переживают рестарт брокера. При необходимости persistence замените `deque` в `broker.py` на SQLite.
- **Нет push** — инстанс сам опрашивает inbox (polling по запросу пользователя или через heartbeat).
- **Нет истории** — только текущие непрочитанные сообщения.
- **Нет ACK** — прочитанные сообщения удаляются только явным `DELETE /inbox`.

---

## Настройка при онбординге

`make add-user` автоматически:
1. Генерирует уникальный `BROKER_KEY`
2. Добавляет `BROKER_KEY_<NAME_UPPER>=<key>` в глобальный `.env`
3. Добавляет `BROKER_KEY=<key>` в `instances/<name>/.env`
4. При `make deploy` брокер подхватывает новый ключ

---

## Примеры использования

**Пользователь 1 просит своего ассистента передать задачу ассистенту Алексея:**
```
Скажи ассистенту Алексея, что нужно подготовить отчёт по спринту к пятнице
```

Ассистент Никиты отправляет:
```bash
curl -X POST http://message-broker:8080/send \
  -H "Authorization: Bearer $BROKER_KEY" \
  -d '{"to":"user-2","message":"Привет от Никиты: нужен отчёт по спринту к пятнице"}'
```

**Пользователь 2 проверяет входящие:**
```bash
curl http://message-broker:8080/inbox -H "Authorization: Bearer $BROKER_KEY"
# → [{"from":"user-1","message":"...","ts":1740672000}]

# После обработки — очищаем
curl -X DELETE http://message-broker:8080/inbox -H "Authorization: Bearer $BROKER_KEY"
```

Скилл `corp-messenger` (в `shared/skills/`) реализует эти вызовы и доступен всем инстансам.
