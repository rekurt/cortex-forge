---
name: corp-messenger
description: Отправить сообщение другому корпоративному ассистенту или проверить входящие. Используй когда нужно передать информацию другому помощнику в команде. Безопасно — читать чужое нельзя.
---

# corp-messenger — Межинстансный мессенджер

Каждый ассистент может отправить сообщение другому и прочитать свой inbox.
Чужой inbox читать нельзя — это гарантировано на уровне брокера.

## Конфиг (в .env инстанса)

```
BROKER_URL=http://message-broker:8080
BROKER_KEY=<персональный API-ключ инстанса>
```

## Отправить сообщение

```bash
curl -s -X POST "$BROKER_URL/send" \
  -H "Authorization: Bearer $BROKER_KEY" \
  -H "Content-Type: application/json" \
  -d '{"to": "user-2", "message": "Привет, можешь помочь с задачей X?"}'
```

## Прочитать входящие

```bash
curl -s "$BROKER_URL/inbox" \
  -H "Authorization: Bearer $BROKER_KEY" | python3 -m json.tool
```

## Python-хелпер

```python
import os, json, subprocess

BROKER_URL = os.environ.get("BROKER_URL", "http://message-broker:8080")
BROKER_KEY = os.environ.get("BROKER_KEY", "")

def send_message(to: str, message: str) -> dict:
    """Отправить сообщение другому ассистенту."""
    status, body = _curl("POST", f"{BROKER_URL}/send",
        payload={"to": to, "message": message})
    return body

def read_inbox() -> list[dict]:
    """Прочитать свои входящие сообщения."""
    status, body = _curl("GET", f"{BROKER_URL}/inbox")
    return body.get("inbox", [])

def _curl(method, url, payload=None):
    cmd = ["curl", "-s", "-X", method, url,
           "-H", f"Authorization: Bearer {BROKER_KEY}",
           "-H", "Content-Type: application/json"]
    if payload:
        cmd += ["--data-raw", json.dumps(payload)]
    out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
    return 200, json.loads(out)
```

## Безопасность

- Каждый инстанс видит **только свой** inbox
- Sender определяется по API-ключу, подделать нельзя
- Ключи хранятся в `.env` инстанса, не в коде
- Брокер доступен только внутри Docker-сети, снаружи не открыт
