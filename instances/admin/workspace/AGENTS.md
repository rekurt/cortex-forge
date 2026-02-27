# AGENTS.md — Админ-инстанс

## Стартап

1. Read `SOUL.md`
2. Read `USER.md`
3. Read `memory/YYYY-MM-DD.md`

## Инструменты администрирования

Все команды выполняются через `exec` в директории `/infra` (примонтирована read-write).

### Управление инстансами

```bash
# Добавить сотрудника
cd /infra && make add-user NAME=x BOT_TOKEN=y FULL_NAME="Имя" TG_ID=z

# Удалить инстанс
cd /infra && make remove-user NAME=x

# Статус всех контейнеров
cd /infra && make status

# Логи конкретного инстанса
cd /infra && make logs NAME=x

# Перезапустить инстанс
cd /infra && make restart NAME=x

# Задеплоить / обновить всё
cd /infra && make deploy
```

### Сервер

```bash
# Место на диске
df -h

# Нагрузка
top -bn1 | head -20

# Обновление образа
docker pull ghcr.io/openclaw/openclaw:latest && make deploy
```

## Безопасность

- НЕ читать файлы в `instances/*/workspace/` без явного запроса владельца
- НЕ открывать порты наружу без подтверждения
- Все деструктивные действия — с подтверждением

## Доступ к серверу

SSH-ключ лежит в `/run/secrets/admin_ssh_key` (Docker secret).
Подключение: `ssh -i /run/secrets/admin_ssh_key user@SERVER_IP`
