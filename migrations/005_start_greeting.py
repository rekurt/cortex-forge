"""При /start всегда запускать corp-greeting, независимо от сессии."""
import pathlib

DESCRIPTION = "run corp-greeting on every /start, not just first session message"

OLD = ("4. **Первое сообщение в сессии** — запусти `corp-greeting` "
       "и используй результат как приветствие")
NEW = ("4. **Первое сообщение в сессии** — запусти `corp-greeting` "
       "и используй результат как приветствие\n"
       "5. **При команде `/start`** — всегда запускай `corp-greeting` заново, "
       "независимо от того, идёт ли уже сессия")

def apply(workspace: pathlib.Path):
    p = workspace / "AGENTS.md"
    if not p.exists():
        return
    text = p.read_text()
    if OLD in text and "При команде" not in text:
        p.write_text(text.replace(OLD, NEW))
