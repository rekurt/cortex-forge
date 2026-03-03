---
name: corp-messenger
description: Отправить сообщение другому корпоративному ассистенту или проверить входящие через общий inbox service-agent. Используй когда нужно передать информацию другому помощнику в команде.
---

# corp-messenger — Межинстансный мессенджер

Все сообщения проходят через service-agent как доверенный прокси.
Service-agent отправляет и читает inbox **от имени caller'а** — получатель видит реального отправителя.

## Вызов через service-agent

Все действия выполняются через HTTP API service-agent.
Endpoint: `POST http://corp-service:8090/v1/run`

**Авторизация:** заголовок `Authorization: Bearer $SERVICE_API_KEY` (переменная окружения `SERVICE_API_KEY`).

### Отправить сообщение

```json
{
  "skill": "corp-messenger",
  "caller": "nikita",
  "params": {
    "action": "send",
    "to": "vasily",
    "message": "Привет, можешь помочь с задачей X?"
  }
}
```

Ответ:
```json
{
  "status": "ok",
  "message": "Sent to vasily",
  "detail": {"ok": true, "from": "nikita", "to": "vasily"}
}
```

### Прочитать входящие

```json
{
  "skill": "corp-messenger",
  "caller": "nikita",
  "params": {
    "action": "inbox"
  }
}
```

Ответ:
```json
{
  "status": "ok",
  "count": 1,
  "inbox": [
    {"from": "vasily", "to": "nikita", "message": "Готово!", "ts": 1709312400.0}
  ]
}
```

### Очистить inbox

```json
{
  "skill": "corp-messenger",
  "caller": "nikita",
  "params": {
    "action": "clear"
  }
}
```

### Список доступных инстансов

```json
{
  "skill": "corp-messenger",
  "caller": "nikita",
  "params": {
    "action": "list"
  }
}
```

Ответ:
```json
{
  "status": "ok",
  "instances": ["admin", "nikita", "vasily", "dmitry"],
  "count": 4
}
```

## Как это работает

- `caller` в запросе определяет, от чьего имени действует skill
- Service-agent выступает доверенным прокси: broker принимает `on_behalf_of` от `service`
- Отправитель в broker = `caller`, не `service`
- Inbox читается для `caller`, не для `service`

## Безопасность

- Прокси-доступ разрешён только `service` и `admin` (PROXY_INSTANCES в broker)
- Sender определяется по caller в запросе к service-agent, подтверждённому через SERVICE_API_KEY
- Ключи хранятся в переменных окружения, не в коде
- Брокер доступен только внутри Docker-сети, снаружи не открыт
- Rate limit: 10 сообщений в минуту
- Максимальный размер сообщения: 10KB
