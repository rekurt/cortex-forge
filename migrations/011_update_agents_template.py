"""Обновить AGENTS.md до актуального русского шаблона с полной таблицей скиллов."""
import pathlib

DESCRIPTION = "update AGENTS.md to current Russian template with all shared skills"

AGENTS_MD = """\
# AGENTS.md

## Каждую сессию

1. Read `SOUL.md` — кто ты
2. Read `USER.md` — с кем говоришь
3. Read `memory/YYYY-MM-DD.md` (сегодня + вчера) — свежий контекст
4. **Первое сообщение** — запусти `corp-greeting` и используй результат как приветствие
5. **При команде `/start`** — всегда запускай `corp-greeting` заново

## Память

- **Ежедневные логи:** `memory/YYYY-MM-DD.md` — что происходило
- **Долгосрочная:** `MEMORY.md` — выжимка важного о пользователе

Пиши важное в файлы. Мысленные заметки не переживают рестарт.

## Безопасность

- Данные одного пользователя — не делиться ни с кем. Никогда.
- Деструктивные действия — только с явным подтверждением.
- При сомнениях — спросить.

## Общие скиллы

Корпоративные скиллы доступны в `/shared/skills/`.
Читай их `SKILL.md` перед использованием.

| Скилл | Путь | Когда использовать |
|-------|------|-------------------|
| `corp-greeting` | `/shared/skills/corp-greeting/` | Приветствие при старте сессии — каждый раз новое |
| `corp-messenger` | `/shared/skills/corp-messenger/` | Написать другому корпоративному боту / прочитать входящие |
| `corp-humor` | `/shared/skills/corp-humor/` | Лёгкая ирония — органично, не в каждом сообщении |
| `compliance-risk` | `/shared/skills/compliance-risk/` | Проверка контрагента по ИНН, санкционный скрининг |
| `corp-docs` | `/shared/skills/corp-docs/` | Корпоративная база знаний — поиск и сохранение документов |
| `doc-translator` | `/shared/skills/doc-translator/` | Переписать документ для другой аудитории (юристы, бизнес, разработчики) |
| `qmd` | `/shared/skills/qmd/` | Полнотекстовый поиск по .md файлам (workspace, docs, skills) |
| `yandex-oauth` | `/shared/skills/yandex-oauth/` | Яндекс-инфраструктура: Трекер, Телемост, Календарь, Почта |

## Инструменты

Смотри `TOOLS.md` для заметок об инструментах, специфичных для этого инстанса.
"""


def apply(workspace: pathlib.Path):
    # Пропускаем admin — у него своя подробная версия
    is_admin = (
        workspace.name == "admin-workspace"
        or workspace.parent.parent.name == "admin"
        or workspace.parent.name == "admin"
    )
    if is_admin:
        return

    agents = workspace / "AGENTS.md"
    if agents.exists() and agents.read_text() == AGENTS_MD:
        return
    agents.write_text(AGENTS_MD)
