# TOOLS.md — Инфраструктура CortexForge (заметки Adminа)

## Текущие инстансы

| Инстанс | Контейнер | Порт | Telegram-бот | Пользователь |
|---------|-----------|------|-------------|-------------|
| admin (Admin) | corp-admin | 18789 | @example_admin_bot | Пользователь 1 (admin) | - это ты
 остальные надо посмотреть заполнить

## Внутренние сервисы

| Сервис | Контейнер | Адрес внутри Docker | Порт на хосте | Назначение |
|--------|-----------|---------------------|---------------|-----------|
| quota-proxy | corp-quota | http://quota-proxy:9090 | 127.0.0.1:9090 | Квотирование API-ключей |
| message-broker | corp-broker | http://message-broker:8080 | — | Межинстансный мессенджер |
| resource-monitor | corp-monitor | http://resource-monitor:9091 | 127.0.0.1:9091 | Метрики Docker-контейнеров |
| service-agent | corp-service | http://assistant-service:8090 | 127.0.0.1:8090 | HTTP API для скиллов |

## Команды для частых операций

### Квоты
```bash
cd /infra && bash scripts/quota.sh report                    # отчёт за месяц
cd /infra && bash scripts/quota.sh set-limit user-1 2000000  # установить лимит
cd /infra && bash scripts/quota.sh reset user-1              # сбросить счётчик
```

### Управление инстансами
```bash
cd /infra && make add-user NAME=x BOT_TOKEN=y FULL_NAME="Имя" TG_ID=z
cd /infra && make remove-user NAME=x
cd /infra && make restart NAME=x
cd /infra && make logs NAME=x
cd /infra && make status
cd /infra && make deploy   # пересобрать и перезапустить всё
```

### Мониторинг
```bash
docker stats --no-stream                          # CPU/RAM
docker ps --format "table {{.Names}}\t{{.Status}}" # статус контейнеров
docker logs corp-user-1 -f --tail=50              # логи инстанса
```

### Миграции
```bash
cd /infra && python3 scripts/migrate-instances.py           # применить миграции
cd /infra && python3 scripts/migrate-instances.py --dry-run # посмотреть что будет
```

## Пути к логам и данным

| Что | Путь на хосте |
|-----|--------------|
| Логи контейнера | `docker logs corp-<name>` |
| База квот (SQLite) | `quota-data` Docker volume → `/data/quota.db` |
| База метрик (SQLite) | `monitor-data` Docker volume → `/data/metrics.db` |
| Данные инстанса | `instances/<name>/openclaw_data/` |
| Воркспейс инстанса | `../<name>-workspace/` (вне репозитория) |
| Shared-скиллы | `shared/skills/` (ro для инстансов) |
| Shared-документы | `shared/docs/` (rw для инстансов) |
| Compliance-данные | `shared/compliance-data/` (ro для инстансов) |
| Секреты проекта | `.env` (только для docker-compose, НЕ монтируется в инстансы) |

## Сети Docker

| Сеть | Тип | Кто подключён | Назначение |
|------|-----|--------------|-----------|
| corp-internal | internal: true | Все контейнеры | Брокер + quota-proxy (нет интернета) |
| corp-admin | internal: true | admin + quota-proxy + monitor | Admin API для квот и метрик |
| corp-egress | bridge | quota-proxy + cliproxyapi | Выход в api.anthropic.com (CLIProxyAPI OAuth) |
| corp-outbound | bridge | admin + инстансы | Telegram API, внешние API |
| corp-services | bridge | service-agent | Backend-интеграции |

---

Этот файл — шпаргалка Adminа. Обновляй при добавлении новых инстансов или сервисов.
