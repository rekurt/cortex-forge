#!/usr/bin/env python3
"""
Генератор приматных шуток для corp-humor.
Запускается Adminом еженедельно через системный крон.
Использует OpenAI API для генерации 20 новых острот.
"""
import json, datetime, pathlib, urllib.request, os

JOKES_FILE = pathlib.Path("/infra/shared/skills/corp-humor/jokes.json")
API_KEY = os.environ.get("OPENAI_API_KEY", "")

if not API_KEY:
    print("OPENAI_API_KEY not set"); exit(1)

PROMPT = """Сгенерируй ровно 20 коротких острот/реплик для корпоративного чат-бота капуцина.

Требования:
- Юмор про приматов, эволюцию, корпоративную жизнь
- Чёрный и саркастический тон, самоирония
- Каждая острота — одна строка, без заголовков и нумерации
- Никаких пояснений — только сами строки
- На русском языке

Выведи 20 строк, каждую с новой строки."""

req_body = json.dumps({
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": PROMPT}],
    "temperature": 0.9,
    "max_tokens": 1000
}).encode()

req = urllib.request.Request(
    "https://api.openai.com/v1/chat/completions",
    data=req_body,
    headers={
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
)

resp = urllib.request.urlopen(req, timeout=30)
data = json.loads(resp.read())
text = data["choices"][0]["message"]["content"].strip()
lines = [l.strip() for l in text.splitlines() if l.strip()][:20]

jokes = {
    "generated_by": "Admin",
    "generated_at": str(datetime.date.today()),
    "lines": lines
}

JOKES_FILE.write_text(json.dumps(jokes, ensure_ascii=False, indent=2))
print(f"✅ Сгенерировано {len(lines)} шуток → {JOKES_FILE}")
