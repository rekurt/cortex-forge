"""Обновить SOUL.md — на основе SOUL.md Клоу, с приматным характером."""
import pathlib

DESCRIPTION = "upgrade SOUL.md — clou-based, capuchin flavour, more sarcasm"

NEW_SOUL = pathlib.Path(__file__).parent.parent / "instances" / "_template" / "workspace" / "SOUL.md"

# Маркеры старых версий — обновляем только если не кастомизировано
OLD_MARKERS = [
    "Деловой, но живой. Как умный коллега, а не корпоративный чат-бот.",  # v1
    "Умный коллега, который не тратит твоё время на вежливые обёртки.",   # v2
]

def apply(workspace: pathlib.Path):
    p = workspace / "SOUL.md"
    if not p.exists():
        return
    text = p.read_text()
    if any(marker in text for marker in OLD_MARKERS):
        p.write_text(NEW_SOUL.read_text())
