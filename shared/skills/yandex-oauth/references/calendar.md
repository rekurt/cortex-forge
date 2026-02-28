# Яндекс Календарь (CalDAV)

## Credentials

```bash
source ~/.secrets/gitlab.env
# YANDEX_CALDAV_URL, YANDEX_USER, YANDEX_APP_PASSWORD
```

> ⚠️ Для CalDAV — **App Password**, не OAuth токен.

## Готовый скрипт (рекомендуется)

```bash
# Посмотреть события на ближайшие N дней
python3 /home/user/.openclaw/workspace/calendar.py --days 7
```

## Чтение событий (curl)

```bash
curl -s -u "$YANDEX_USER:$YANDEX_APP_PASSWORD" \
  -X REPORT "$YANDEX_CALDAV_URL" \
  -H "Content-Type: application/xml" \
  -d '<?xml version="1.0" encoding="UTF-8"?>
<c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
  <d:prop><d:getetag/><c:calendar-data/></d:prop>
  <c:filter>
    <c:comp-filter name="VCALENDAR">
      <c:comp-filter name="VEVENT">
        <c:time-range start="20260101T000000Z" end="20261231T235959Z"/>
      </c:comp-filter>
    </c:comp-filter>
  </c:filter>
</c:calendar-query>'
```

## Создать событие (iCalendar PUT)

```bash
source ~/.secrets/gitlab.env
UUID=$(uuidgen)
curl -s -u "$YANDEX_USER:$YANDEX_APP_PASSWORD" \
  -X PUT "$YANDEX_CALDAV_URL/$UUID.ics" \
  -H "Content-Type: text/calendar; charset=utf-8" \
  -d "BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:$UUID
SUMMARY:Название встречи
DESCRIPTION:Описание\nСсылка: https://telemost.yandex.ru/j/...
DTSTART:20260301T150000Z
DTEND:20260301T160000Z
END:VEVENT
END:VCALENDAR"
```

## Формат дат

- UTC: `YYYYMMDDTHHMMSSZ`
- С timezone: `TZID=Europe/Moscow:YYYYMMDDTHHMMSS`
- Московское время = UTC+3

## Workflow — добавить событие после создания Телемоста

1. Создай конференцию Телемост → получи `join_url`
2. Сформируй iCalendar с `DESCRIPTION: join_url`
3. `PUT` в CalDAV с уникальным UUID
4. Подтверди пользователю
