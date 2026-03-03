---
name: qmd
description: Быстрый полнотекстовый поиск по .md файлам системы. Ищет по workspace, shared docs, skills. Поддерживает regex. Используй когда нужно найти информацию в документации или базе знаний.
---

# qmd — Поиск по Markdown файлам

Быстрый поиск по всем .md файлам CortexForge: workspace, shared docs, skills.
Поддерживает обычный текст и regex.

## Вызов через service-agent

Endpoint: `POST http://corp-service:8090/v1/run`

### Простой поиск

```json
{
  "skill": "qmd",
  "caller": "user-1",
  "params": {
    "query": "quota"
  }
}
```

### Поиск с фильтром по scope

```json
{
  "skill": "qmd",
  "caller": "user-1",
  "params": {
    "query": "BROKER_KEY",
    "scope": "shared",
    "max_results": 5
  }
}
```

### Поиск с regex

```json
{
  "skill": "qmd",
  "caller": "user-1",
  "params": {
    "query": "quota[_-]proxy|rate.limit",
    "scope": "all"
  }
}
```

## Параметры

| Параметр | Тип | Обязательный | Описание |
|----------|-----|--------------|----------|
| query | string | да | Поисковый запрос (текст или regex) |
| scope | string | нет | Область поиска: `all` (по умолчанию), `workspace`, `shared`, `skills` |
| max_results | integer | нет | Максимум файлов в результатах (по умолчанию 10, максимум 50) |

## Области поиска (scope)

| Scope | Директории |
|-------|-----------|
| `workspace` | /home/node/.openclaw/workspace/ (твой workspace) |
| `shared` | /shared/docs/ + /shared/skills/ |
| `skills` | /shared/skills/ only |
| `all` | Все вышеперечисленные |

## Пример ответа

```json
{
  "status": "ok",
  "query": "quota",
  "scope": "all",
  "results": [
    {
      "file": "/shared/docs/architecture.md",
      "match_count": 3,
      "matches": [
        {
          "line_number": 42,
          "context": "## Quota System\n\nquota-proxy контролирует расход токенов..."
        }
      ]
    }
  ],
  "total_files_with_matches": 1,
  "total_matches": 3,
  "files_scanned": 15,
  "elapsed_ms": 45
}
```

## Ограничения

- Файлы больше 512 KB пропускаются
- Таймаут поиска: 10 секунд
- Максимум 5 совпадений на файл в результатах
- Максимум 50 файлов в результатах
