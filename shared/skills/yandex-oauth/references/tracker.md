# Яндекс Трекер

## Credentials

```bash
source ~/.secrets/gitlab.env
# YANDEX_OAUTH_TOKEN, YANDEX_ORG_ID
```

Headers для всех запросов:
```
Authorization: OAuth {YANDEX_OAUTH_TOKEN}
X-Cloud-Org-ID: {YANDEX_ORG_ID}   # bpfnki0i3febm8l2rgt5
Content-Type: application/json
```

Base URL: `https://api.tracker.yandex.net/v2`

## Готовый скрипт

```bash
python3 /home/user/.openclaw/workspace/tracker.py
```

## Создать задачу

```
POST /v2/issues
```

```json
{
  "queue": "BACK",
  "summary": "Название задачи",
  "description": "Описание задачи",
  "assignee": "username",
  "type": "task",
  "priority": "normal",
  "deadline": "2026-03-15",
  "tags": ["relayer", "network-swap"]
}
```

Ответ: `{"key": "BACK-123", "self": "https://api.tracker.yandex.net/v2/issues/BACK-123"}`
Ссылка для пользователя: `https://tracker.yandex.ru/{KEY}`

## Поиск задач

```
POST /v2/issues/_search?perPage=10

{
  "query": "Summary: ~\"ключевое слово\" AND Status: !closed"
}
```

С фильтром по времени:
```json
{"query": "UpdatedAt: >= now()-7d AND Queue: BACK"}
```

## Задачи на меня

```
GET /v2/issues?filter[assignee]=me()&filter[status]=!closed
```

## Очереди

| Ключ | Назначение |
|---|---|
| `BACK` | Backend |
| `FRONT` | Frontend |
| `PRODUCT` | Бизнес, эпики |
| `DEVOPS` | Инфраструктура |
| `ML` | AI/ML задачи |
| `SAST` | Безопасность |

## Параметры задачи

- `priority`: `blocker`, `critical`, `normal`, `minor`, `trivial`
- `type`: `task`, `bug`, `improvement`, `epic`
- `assignee`: логин из Трекера (например `n.aldaev`, `i.dergachev`)

## Пример curl

```bash
source ~/.secrets/gitlab.env
curl -s -X POST https://api.tracker.yandex.net/v2/issues \
  -H "Authorization: OAuth $YANDEX_OAUTH_TOKEN" \
  -H "X-Cloud-Org-ID: $YANDEX_ORG_ID" \
  -H "Content-Type: application/json" \
  -d '{"queue":"BACK","summary":"Тест","type":"task","priority":"normal"}'
```
