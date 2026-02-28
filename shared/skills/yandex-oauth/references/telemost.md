# Яндекс Телемост

## Создать конференцию

```
POST https://cloud-api.yandex.net/v1/telemost/conferences
Authorization: OAuth {YANDEX_OAUTH_TOKEN}
Content-Type: application/json

{}
```

**Ответ:**
```json
{
  "join_url": "https://telemost.yandex.ru/j/...",
  "id": "conf_id_..."
}
```

## Получить конференцию

```
GET https://cloud-api.yandex.net/v1/telemost/conferences/{id}
Authorization: OAuth {YANDEX_OAUTH_TOKEN}
```

## Workflow — создать митинг

1. Уточни детали (если не указаны):
   - Название / тема
   - Дата и время
   - Участники
   - Продолжительность (по умолчанию 1 час)
2. `POST /conferences` → получи `join_url`
3. Добавь событие в Яндекс Календарь → см. [calendar.md](calendar.md)
4. Верни пользователю: ссылку + детали события

## Пример curl

```bash
source ~/.secrets/gitlab.env
curl -s -X POST https://cloud-api.yandex.net/v1/telemost/conferences \
  -H "Authorization: OAuth $YANDEX_OAUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'
```
