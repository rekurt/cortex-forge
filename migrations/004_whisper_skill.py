"""Добавить openai-whisper-api и openai-image-gen в openclaw.json инстанса."""
import pathlib
import json

DESCRIPTION = "add openai-whisper-api + image-gen to openclaw.json"

def apply(workspace: pathlib.Path):
    # openclaw.json лежит на уровень выше workspace
    cfg_path = workspace.parent / "openclaw.json"
    if not cfg_path.exists():
        return

    raw = cfg_path.read_text()

    # Не трогаем если уже есть
    if "openai-whisper-api" in raw:
        return

    # Подставляем как строку — файл содержит ${ENV_VAR} плейсхолдеры
    skills_block = ''',
  "skills": {
    "entries": {
      "openai-whisper-api": {
        "apiKey": "${OPENAI_API_KEY}"
      },
      "openai-image-gen": {
        "apiKey": "${OPENAI_API_KEY}"
      }
    }
  }'''

    # Вставляем перед последней закрывающей скобкой
    new_raw = raw.rstrip().rstrip("}") + skills_block + "\n}"
    cfg_path.write_text(new_raw)
