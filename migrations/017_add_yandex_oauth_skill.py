"""Добавить yandex-oauth в таблицу скиллов AGENTS.md каждого инстанса."""
import pathlib

DESCRIPTION = "add yandex-oauth to shared skills table in AGENTS.md"

NEW_ROW = '| `yandex-oauth` | `/shared/skills/yandex-oauth/` | Яндекс OAuth: Трекер, Телемост, Календарь (CalDAV) — единая точка входа |\n'
ANCHOR = '| `compliance-risk`'


def apply(workspace: pathlib.Path):
    agents_md = workspace / "AGENTS.md"
    if not agents_md.exists():
        return "нет AGENTS.md — пропускаем"

    text = agents_md.read_text()

    if "yandex-oauth" in text:
        return "уже есть"

    if ANCHOR in text:
        text = text.replace(ANCHOR, NEW_ROW + ANCHOR, 1)
    else:
        # fallback — добавим в конец файла
        text = text.rstrip() + "\n" + NEW_ROW

    agents_md.write_text(text)
    return "yandex-oauth добавлен в таблицу скиллов"
