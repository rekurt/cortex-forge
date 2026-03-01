---
name: corp-messenger
description: Отправить сообщение другому корпоративному ассистенту или проверить входящие. Используй когда нужно передать информацию другому помощнику в команде. Безопасно — читать чужое нельзя.
---

# corp-messenger — Межинстансный мессенджер

Каждый ассистент может отправить сообщение другому и прочитать свой inbox.
Чужой inbox читать нельзя — это гарантировано на уровне брокера.

## Вызов через service-agent

Все действия выполняются через HTTP API service-agent.
Endpoint: `POST http://corp-service:8090/v1/run`

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
  "detail": {"ok": true, "from": "service", "to": "vasily"}
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
  "count": 2,
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

## Безопасность

- Каждый инстанс видит **только свой** inbox
- Sender определяется по BROKER_KEY service-agent, подделать нельзя
- Ключи хранятся в переменных окружения, не в коде
- Брокер доступен только внутри Docker-сети, снаружи не открыт
- Rate limit: 10 сообщений в минуту
- Максимальный размер сообщения: 10KB
