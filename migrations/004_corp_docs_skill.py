"""Добавить corp-docs в AGENTS.md: строка в таблице скиллов."""
import pathlib

DESCRIPTION = "add corp-docs skill to AGENTS.md"

def apply(workspace: pathlib.Path):
    p = workspace / "AGENTS.md"
    if not p.exists():
        return
    text = p.read_text()

    if "corp-docs" in text:
        return

    new_row = ("| `corp-docs` | `/shared/skills/corp-docs/` "
               "| Сохранить и найти документы в общей базе знаний |")

    # Вставляем перед corp-humor если есть
    if "| `corp-humor`" in text:
        text = text.replace(
            "| `corp-humor`",
            new_row + "\n| `corp-humor`"
        )
    else:
        # Добавляем после последней строки таблицы скиллов
        text += f"\n{new_row}\n"

    p.write_text(text)
