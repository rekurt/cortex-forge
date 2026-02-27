"""Добавить corp-greeting в AGENTS.md: шаг 4 + строка в таблице скиллов."""
import pathlib

DESCRIPTION = "add corp-greeting skill to AGENTS.md"

def apply(workspace: pathlib.Path):
    p = workspace / "AGENTS.md"
    if not p.exists():
        return
    text = p.read_text()

    # Шаг 4 в Every Session
    old_step = "3. Read `memory/YYYY-MM-DD.md` for recent context"
    new_step  = (old_step + "\n"
                 "4. **Первое сообщение в сессии** — запусти `corp-greeting` "
                 "и используй результат как приветствие")
    if old_step in text and "corp-greeting" not in text:
        text = text.replace(old_step, new_step)

    # Строка в таблице
    old_row = ("| `compliance-risk` | `/shared/skills/compliance-risk/SKILL.md` "
               "| Проверка контрагента по ИНН/ОГРН/УНП/БИН, AML/KYC оценка риска, "
               "санкционный скрининг |")
    new_rows = (old_row + "\n"
                "| `corp-greeting` | `/shared/skills/corp-greeting/SKILL.md` "
                "| Приветствие при старте сессии — каждый раз новое |")
    if old_row in text and "corp-greeting/SKILL.md" not in text:
        text = text.replace(old_row, new_rows)

    p.write_text(text)
