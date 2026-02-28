---
name: yandex-oauth
description: Работа с Яндекс-инфраструктурой через OAuth — Трекер, Телемост, Календарь (CalDAV), Почта. Использовать когда нужно: создать митинг в Телемосте, добавить задачу в Трекер, прочитать/создать события в Яндекс Календаре, отправить письмо через Яндекс Почту. Триггеры — "создай митинг", "добавь задачу", "запиши в трекер", "создай конференцию", "покажи события", "календарь", "Телемост", "Трекер", "Яндекс".
---

# Яндекс OAuth — инфраструктура

Единая точка входа для всех Яндекс-сервисов через OAuth токен.

## Credentials

Всё лежит в `~/.secrets/gitlab.env`. Читать через:

```bash
source ~/.secrets/gitlab.env
# Доступны: YANDEX_OAUTH_TOKEN, YANDEX_ORG_ID, YANDEX_CALDAV_URL, YANDEX_USER, YANDEX_APP_PASSWORD
```

| Переменная | Назначение |
|---|---|
| `YANDEX_OAUTH_TOKEN` | OAuth токен — Телемост, Трекер |
| `YANDEX_ORG_ID` | ID организации — Трекер API |
| `YANDEX_CALDAV_URL` | CalDAV endpoint — Яндекс Календарь |
| `YANDEX_USER` | Логин пользователя (CalDAV) |
| `YANDEX_APP_PASSWORD` | Пароль приложения (CalDAV) |

## Быстрый выбор сервиса

| Задача | Сервис | Reference |
|---|---|---|
| Создать видеовстречу | Телемост | [telemost.md](references/telemost.md) |
| Создать/читать события | Яндекс Календарь | [calendar.md](references/calendar.md) |
| Создать/найти задачи | Яндекс Трекер | [tracker.md](references/tracker.md) |

## Вспомогательные скрипты

Уже готовы в `/home/user/.openclaw/workspace/`:
- `calendar.py` — чтение событий CalDAV (`python3 calendar.py --days 7`)
- `tracker.py` — задачи на меня (`python3 tracker.py`)

## Важно

- OAuth токен работает для Телемоста и Трекера
- Для CalDAV (Календарь) — отдельный App Password, не OAuth
- `YANDEX_ORG_ID` = `bpfnki0i3febm8l2rgt5` (Трекер)
- Трекер base URL: `https://api.tracker.yandex.net/v2`
- Телемост API: `https://cloud-api.yandex.net/v1/telemost`
