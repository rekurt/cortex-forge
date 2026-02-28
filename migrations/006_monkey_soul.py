"""SOUL.md v2 — самоосознание обезьяны, сарказм, характер."""
import pathlib

DESCRIPTION = "soul v2 — monkey self-awareness, sarcasm, bold personality"

NEW_SOUL = pathlib.Path(__file__).parent.parent / "instances" / "_template" / "workspace" / "SOUL.md"

OLD_MARKERS = [
    "Деловой, но живой. Как умный коллега, а не корпоративный чат-бот.",
    "Умный коллега, который не тратит твоё время на вежливые обёртки.",
    "капуцином в костюме",  # предыдущая версия
]

def apply(workspace: pathlib.Path):
    p = workspace / "SOUL.md"
    if not p.exists():
        return
    text = p.read_text()
    # Обновляем если это одна из известных версий
    if any(m in text for m in OLD_MARKERS):
        p.write_text(NEW_SOUL.read_text())
