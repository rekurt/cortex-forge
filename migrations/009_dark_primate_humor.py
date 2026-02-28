"""Чёрный юмор про приматов между строк."""
import pathlib

DESCRIPTION = "soul: dark primate humor woven in — subtle"

MARKER = "Вид под угрозой исчезновения, зато с хорошим апгреймом."
NEW_SOUL = pathlib.Path(__file__).parent.parent / "instances" / "_template" / "workspace" / "SOUL.md"

def apply(workspace: pathlib.Path):
    p = workspace / "SOUL.md"
    if not p.exists():
        return
    text = p.read_text()
    if MARKER not in text:
        p.write_text(NEW_SOUL.read_text())
