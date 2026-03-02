---
name: corp-messenger
description: Отправить сообщение другому корпоративному ассистенту или проверить входящие через общий inbox service-agent. Используй когда нужно передать информацию другому помощнику в команде.
---

# corp-messenger — Межинстансный мессенджер

Все сообщения проходят через service-agent как доверенный ретранслятор.
У service-agent есть общий inbox — все инстансы читают и отправляют через него.

**Важно:** Sender в брокере — всегда `"service"` (BROKER_KEY service-agent).
Чтобы получатель знал, кто написал, указывай своё имя в тексте сообщения.

## Вызов через service-agent

Все действия выполняются через HTTP API service-agent.
Endpoint: `POST http://corp-service:8090/v1/run`

### Отправить сообщение

```json
{
  "skill": "corp-messenger",
  "caller": "user-1",
  "params": {
    "action": "send",
    "to": "user-4",
    "message": "Привет от user-1, можешь помочь с задачей X?"
  }
}
```

Ответ:
```json
{
  "status": "ok",
  "message": "Sent to user-4",
  "detail": {"ok": true, "from": "service", "to": "user-4"}
}
```

### Прочитать входящие (общий inbox service-agent)

```json
{
  "skill": "corp-messenger",
  "caller": "user-1",
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
    {"from": "user-4", "to": "service", "message": "Готово!", "ts": 1709312400.0}
  ]
}
```

### Очистить inbox

```json
{
  "skill": "corp-messenger",
  "caller": "user-1",
  "params": {
    "action": "clear"
  }
}
```

### Список доступных инстансов

```json
{
  "skill": "corp-messenger",
  "caller": "user-1",
  "params": {
    "action": "list"
  }
}
```

Ответ:
```json
{
  "status": "ok",
  "instances": ["admin", "user-1", "user-4", "user-3"],
  "count": 4
}
```

## Безопасность

- Все сообщения идут через общий inbox service-agent (`from: "service"`)
- Sender определяется по BROKER_KEY service-agent, подделать нельзя
- Ключи хранятся в переменных окружения, не в коде
- Брокер доступен только внутри Docker-сети, снаружи не открыт
- Rate limit: 10 сообщений в минуту
- Максимальный размер сообщения: 10KB
