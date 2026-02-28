"""Добавить doc-translator в таблицу скиллов AGENTS.md каждого инстанса."""
import pathlib

DESCRIPTION = "add doc-translator to shared skills table in AGENTS.md"

NEW_ROW = '| `doc-translator` | `/shared/skills/doc-translator/` | Переписать документ для другой аудитории (dev↔бизнес↔юристы↔инвесторы) |\n'
ANCHOR = '| `yandex-oauth`'


def apply(workspace: pathlib.Path):
    agents_md = workspace / "AGENTS.md"
    if not agents_md.exists():
        return "нет AGENTS.md — пропускаем"

    text = agents_md.read_text()

    if "doc-translator" in text:
        return "уже есть"

    if ANCHOR in text:
        text = text.replace(ANCHOR, NEW_ROW + ANCHOR, 1)
    else:
        text = text.rstrip() + "\n" + NEW_ROW

    agents_md.write_text(text)
    return "doc-translator добавлен в таблицу скиллов"
