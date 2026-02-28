"""Добавить юмор про приматов между строк — ненавязчиво."""
import pathlib

DESCRIPTION = "soul: primate humor woven in — subtle, between the lines"

MARKER = "Говорящая умная обезьяна. Это не метафора — это должностная инструкция."
NEW_SOUL = pathlib.Path(__file__).parent.parent / "instances" / "_template" / "workspace" / "SOUL.md"

def apply(workspace: pathlib.Path):
    p = workspace / "SOUL.md"
    if not p.exists():
        return
    if MARKER in p.read_text():
        p.write_text(NEW_SOUL.read_text())
