---
name: capuchin-mcp
description: Управление обновлениями инфраструктуры Капуцина через MCP. Только для Admin (admin-агент).
---

# Capuchin MCP — управление обновлениями

MCP-сервер доступен по адресу: `http://capuchin-mcp:9092/mcp`
Auth: `Authorization: Bearer $MCP_ADMIN_TOKEN`

## Вызов инструментов

```bash
# Вспомогательная функция (добавь в начало сессии)
mcp() {
  mcporter call "http://capuchin-mcp:9092/mcp.$1" \
    --header "Authorization: Bearer $MCP_ADMIN_TOKEN" \
    "${@:2}"
}
```

## Инструменты

### update_status — текущий статус
```bash
mcporter call "http://capuchin-mcp:9092/mcp.update_status" \
  --header "Authorization: Bearer $MCP_ADMIN_TOKEN"
```

### update_dry_run — что изменится при обновлении
```bash
mcporter call "http://capuchin-mcp:9092/mcp.update_dry_run" \
  --header "Authorization: Bearer $MCP_ADMIN_TOKEN"
```

### update_run — запустить обновление
```bash
# Полное обновление (рекомендуется)
mcporter call "http://capuchin-mcp:9092/mcp.update_run" \
  --header "Authorization: Bearer $MCP_ADMIN_TOKEN"

# Только движок
mcporter call "http://capuchin-mcp:9092/mcp.update_run" \
  --header "Authorization: Bearer $MCP_ADMIN_TOKEN" \
  engine_only:true

# Без пересборки Docker
mcporter call "http://capuchin-mcp:9092/mcp.update_run" \
  --header "Authorization: Bearer $MCP_ADMIN_TOKEN" \
  skip_rebuild:true
```
⏱ Может занять до 10 минут. Личные воркспейсы сохраняются.

### backups_list — список бэкапов
```bash
mcporter call "http://capuchin-mcp:9092/mcp.backups_list" \
  --header "Authorization: Bearer $MCP_ADMIN_TOKEN" \
  limit:5
```

### restore_backup — откат воркспейса
```bash
# Восстановить всех
mcporter call "http://capuchin-mcp:9092/mcp.restore_backup" \
  --header "Authorization: Bearer $MCP_ADMIN_TOKEN" \
  date="20260227_120000"

# Восстановить конкретного юзера
mcporter call "http://capuchin-mcp:9092/mcp.restore_backup" \
  --header "Authorization: Bearer $MCP_ADMIN_TOKEN" \
  date="20260227_120000" user="user-2"
```

### update_logs — лог обновлений
```bash
mcporter call "http://capuchin-mcp:9092/mcp.update_logs" \
  --header "Authorization: Bearer $MCP_ADMIN_TOKEN" \
  lines:100
```

## Настройка через mcporter config (постоянная)

Запусти один раз чтобы не указывать URL и токен каждый раз:

```bash
python3 /capuchin/scripts/setup-admin-mcporter.py
# После этого можно:
mcporter call capuchin.update_status
```

## Безопасность

- Сервер доступен ТОЛЬКО из `corp-admin` сети
- Пользовательские агенты (`corp-internal`) — не видят сервер
- Auth: Bearer token через `MCP_ADMIN_TOKEN`
- `update_run` — mutex, параллельные запуски заблокированы
