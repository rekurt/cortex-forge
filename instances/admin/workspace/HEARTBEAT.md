# HEARTBEAT.md — Приор

## Задачи

### 🐒 Обновление пула шуток (раз в неделю)
Проверь дату в `/infra/shared/skills/corp-humor/jokes.json` (поле `generated_at`).
Если прошло больше 7 дней — сгенерируй 20 новых острот про приматов в корпоративной среде:
- Чёрный юмор, самоирония, ирония над эволюцией, корпоративной жизнью, плеском
- Одна строка — одна шутка, без пояснений
- Запиши в файл через exec:

```python
import json, datetime, pathlib
jokes = {
    "generated_by": "Приор",
    "generated_at": str(datetime.date.today()),
    "lines": [
        # ... твои 20 шуток ...
    ]
}
pathlib.Path("/infra/shared/skills/corp-humor/jokes.json").write_text(
    json.dumps(jokes, ensure_ascii=False, indent=2)
)
```

Если всё в порядке — HEARTBEAT_OK.
