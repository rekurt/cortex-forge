"""Добавить в SOUL.md правило: при вопросе 'что ты умеешь' — прислать welcome.md из общих доков."""
import pathlib

MIGRATION_ID = "019_welcome_on_capabilities"
DESCRIPTION = "при вопросе что умеешь — читать /shared/docs/common/welcome.md"

BLOCK = """
---

## Что умеешь — велком-заметка

Если тебя спрашивают «что ты умеешь», «что можешь», «как пользоваться», «что ты такое» —
прочитай файл `/shared/docs/common/welcome.md` и отправь его содержимое пользователю.
Без лишних слов от себя — просто заметка. Можно добавить одну фразу сверху максимум.
"""


def apply(workspace: pathlib.Path):
    soul_path = workspace / "SOUL.md"
    if not soul_path.exists():
        return "SOUL.md не найден — пропущено"

    content = soul_path.read_text()

    if "велком-заметка" in content:
        return "уже есть"

    soul_path.write_text(content.rstrip() + "\n" + BLOCK)
    return "Добавлен блок 'велком-заметка' в SOUL.md"
