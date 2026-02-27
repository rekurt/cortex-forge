# Migrations

Пронумерованные миграции воркспейса инстансов. Применяются автоматически при `git pull` через `post-merge` хук.

## Формат

```python
# migrations/NNN_описание.py
DESCRIPTION = "что делает миграция"

def apply(workspace: pathlib.Path):
    """workspace — путь к instances/<name>/openclaw_data/workspace/"""
    ...
```

## Правила

- Имя файла: `NNN_snake_case.py` (NNN — трёхзначный номер)
- `apply()` должна быть **идемпотентной** — проверять, нужно ли изменение
- Не трогать личные файлы (`MEMORY.md`, `memory/`, персонализированные `USER.md`, `SOUL.md` с кастомным контентом)
- Уже применённые миграции записываются в `workspace/.migrations_applied` (gitignored)
