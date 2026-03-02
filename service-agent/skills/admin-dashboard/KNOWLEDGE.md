# CortexForge Admin Knowledge Base

Полный справочник по управлению CortexForge. Используй эту базу знаний для диагностики и операций.

## 1. Архитектура ключей

### Карта ключей

| Переменная | Где живёт | Значение | Кто использует |
|---|---|---|---|
| ANTHROPIC_API_KEY (корневой .env) | Только quota-proxy | sk-ant-xxx (реальный ключ) | quota-proxy для форвардинга в api.anthropic.com |
| ANTHROPIC_API_KEY (в docker env инстанса) | docker-compose.yml | = QUOTA_KEY_USER_1 (НЕ реальный ключ!) | OpenClaw через openclaw.json |
| QUOTA_KEY_\<NAME\> | Корневой .env → docker-compose.yml mapping | quota-\<name\>-xxx | Подставляется как ANTHROPIC_API_KEY инстанса |
| QUOTA_ADMIN_TOKEN | Корневой .env | 32+ символов | Admin API quota-proxy, admin-dashboard |
| BROKER_KEY_\<NAME\> | Корневой .env | Рандомная строка | Аутентификация в broker |
| SERVICE_API_KEY | Корневой .env | svc-xxx | Аутентификация в service-agent |
| MONITOR_ADMIN_TOKEN | Корневой .env | Рандомная строка | Admin API resource-monitor |

### Как работает quota-proxy (поток запроса)

1. OpenClaw шлёт запрос на baseUrl (http://quota-proxy:9090) с x-api-key = ANTHROPIC_API_KEY (из env = QUOTA_KEY_\*)
2. quota-proxy хэширует ключ через SHA256
3. Сравнивает с хэшами QUOTA_KEY_\* из корневого .env (constant-time через hmac.compare_digest)
4. Если совпал — определяет имя инстанса, проверяет лимит
5. Подставляет РЕАЛЬНЫЙ sk-ant-xxx ключ и форвардит в api.anthropic.com
6. Логирует расход токенов в SQLite

### Почему в openclaw.json стоит ANTHROPIC_API_KEY = quota key

- openclaw.json.template содержит `"apiKey": "${ANTHROPIC_API_KEY}"`
- Docker Compose маппит: `ANTHROPIC_API_KEY=${QUOTA_KEY_USER_1}`
- OpenClaw видит env-переменную ANTHROPIC_API_KEY, подставляет в apiKey
- Результат: запрос идёт на quota-proxy с quota key, proxy подменяет на реальный

## 2. Сети Docker

| Сеть | Тип | Кто подключён | Назначение |
|---|---|---|---|
| corp-internal | internal: true | Все инстансы, broker, quota-proxy, monitor, service-agent | Внутренняя шина. Нет выхода в интернет |
| corp-admin | internal: true | quota-proxy, monitor, admin | Управление квотами и метриками |
| corp-egress | bridge (не internal) | ТОЛЬКО quota-proxy | Единственный выход к api.anthropic.com |
| corp-outbound | bridge (не internal) | admin, инстансы | Telegram API, внешние сервисы |
| corp-services | bridge | service-agent | Backend-интеграции |

Ключевой принцип: инстансы НЕ могут напрямую обратиться к api.anthropic.com. Все AI-запросы идут через quota-proxy.

## 3. Частые ошибки и решения

### "Instance can't authenticate" / "Unknown quota key"
- Причина: QUOTA_KEY_\<NAME\> не задан или не совпадает
- Проверка: `grep QUOTA_KEY_ .env`
- Решение: убедись что ключ в .env совпадает с тем, что видит quota-proxy
- Перезапуск: `docker compose restart quota-proxy`

### "Broker 403" / "Unauthorized"
- Причина: BROKER_KEY_\<NAME\> не задан или не совпадает
- Проверка: `grep BROKER_KEY_ .env`
- Решение: проверь что ключ в .env, добавь если нет
- Перезапуск: `docker compose restart message-broker`

### "Quota exceeded" / "429"
- Причина: инстанс превысил месячный лимит токенов
- Проверка: `make quota-report` или admin-dashboard action=overview
- Решение: `make set-limit NAME=<имя> LIMIT=<число>` или `make quota-reset NAME=<имя>`

### "Container unhealthy"
- Проверка: `docker compose ps`
- Логи: `docker compose logs <service-name> --tail 50`
- Решение: `docker compose restart <service-name>`
- Если не помогает: `docker compose up -d --build <service-name>`

### "Rate limit exceeded" (quota-proxy)
- 300 proxy-запросов/мин на инстанс, 60 admin-запросов/мин на IP
- Подожди минуту и повтори

### "Connection failed" к внутренним сервисам
- Проверь что контейнер запущен: `docker compose ps`
- Проверь что контейнер на правильной сети: `docker network inspect corp-internal`
- Перезапусти: `docker compose restart <service-name>`

## 4. Пошаговые инструкции

### Добавить нового сотрудника
```
make add-user NAME=user-2 BOT_TOKEN=7xxx FULL_NAME="Пользователь 2" TG_ID=123456789
docker compose up -d
docker compose logs assistant-user-2 --tail 20
```

### Удалить сотрудника
```
make remove-user NAME=user-2
docker compose up -d
```

### Изменить лимит токенов (без рестарта)
```
make set-limit NAME=user-2 LIMIT=500000
```
Или через admin-dashboard: action=set-limit, name=user-2, limit=500000

### Сбросить счётчик токенов
```
make quota-reset NAME=user-2
```
Или через admin-dashboard: action=reset-quota, name=user-2

### Посмотреть использование токенов
```
make quota-report
make quota-report MONTH=2026-03
```
Или через admin-dashboard: action=overview

### Перезапустить инстанс
```
make restart NAME=user-2
```

### Полный деплой
```
make deploy
docker compose ps
```

### Бэкап всех воркспейсов
```
make backup
```

## 5. Danger Zone — НИКОГДА НЕ ДЕЛАЙ

- НИКОГДА не копируй ANTHROPIC_API_KEY из корневого .env в инстанс
- НИКОГДА не редактируй .env файлы инстансов вручную через docker exec
- НИКОГДА не меняй QUOTA_KEY_\* без рестарта quota-proxy
- НИКОГДА не давай инстансу прямой ключ к Anthropic API
- НИКОГДА не подключай инстансы к сети corp-egress
- НИКОГДА не удаляй volume quota-data или broker-data без бэкапа
- НИКОГДА не запускай docker compose down -v (удалит все volumes!)

## 6. Мониторинг

### Какие метрики смотреть

| Метрика | Норма | Алерт |
|---|---|---|
| CPU контейнера | < 50% | > 80% |
| RAM контейнера | < 70% лимита | > 85% лимита |
| Диск хоста | < 80% | > 90% |
| Квота токенов | < 80% | > 80% |

### Команды мониторинга
```
make monitor              # CPU/RAM/disk
make monitor-alerts       # активные алерты
make status               # docker compose ps
make quota-report         # использование токенов
```

### API эндпоинты (внутренние)

| Сервис | URL | Auth | Назначение |
|---|---|---|---|
| quota-proxy | http://quota-proxy:9090/quota/health | нет | Статус, список инстансов |
| quota-proxy | http://quota-proxy:9090/quota/report | Bearer QUOTA_ADMIN_TOKEN | Отчёт по квотам |
| quota-proxy | http://quota-proxy:9090/quota/set-limit | Bearer QUOTA_ADMIN_TOKEN | Изменить лимит (POST) |
| quota-proxy | http://quota-proxy:9090/quota/reset | Bearer QUOTA_ADMIN_TOKEN | Сбросить квоту (POST) |
| monitor | http://resource-monitor:9091/health | нет | Healthcheck |
| monitor | http://resource-monitor:9091/metrics | нет* | Метрики контейнеров + диск + квоты |
| monitor | http://resource-monitor:9091/alerts/active | нет* | Активные алерты |
| broker | http://message-broker:8080/health | нет | Статус, список инстансов, count |
| broker | http://message-broker:8080/send | Bearer BROKER_KEY_\* | Отправить сообщение (POST) |
| broker | http://message-broker:8080/inbox | Bearer BROKER_KEY_\* | Прочитать inbox (GET) |
| service-agent | http://corp-service:8090/v1/health | нет | Healthcheck |
| service-agent | http://corp-service:8090/v1/skills | Bearer SERVICE_API_KEY | Список скиллов |
| service-agent | http://corp-service:8090/v1/run | Bearer SERVICE_API_KEY | Запустить скилл (POST) |

\* monitor auth опциональна (MONITOR_ADMIN_TOKEN)
