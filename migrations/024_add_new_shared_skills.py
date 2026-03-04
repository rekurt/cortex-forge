"""
Migration 024: Добавить 7 новых shared-скиллов в таблицу AGENTS.md всех инстансов
"""

MIGRATION_ID = "024_add_new_shared_skills"

import os

NEW_SKILLS = [
    ("standup-digest",   "/shared/skills/standup-digest/",   "Ежедневный стендап-дайджест открытых MR из GitLab — будни в 7:00 MSK"),
    ("news-digest",      "/shared/skills/news-digest/",      "Дайджест новостей (AI, Крипто, Dev, Мир) через blogwatcher — 9:00 и 19:00 MSK"),
    ("morning-briefing", "/shared/skills/morning-briefing/", "Утренний брифинг: календарь, Трекер, GitLab MR, почта — один дайджест в 9:00 MSK"),
    ("gitlab-changelog", "/shared/skills/gitlab-changelog/", "Changelog из GitLab MR перед релизом — группирует по категориям (фичи, фиксы, рефакторинг)"),
    ("release-notes",    "/shared/skills/release-notes/",    "Human-friendly release notes для команды в Telegram — по-русски, без технических деталей"),
    ("dep-audit",        "/shared/skills/dep-audit/",        "Аудит Go-зависимостей: устаревшие и уязвимые пакеты (go.mod из GitLab)"),
    ("sast-priority",    "/shared/skills/sast-priority/",    "Еженедельный топ-10 задач из очереди SAST в Трекере — по severity и давности"),
]

# Вставляем перед этим якорем (после gitlab-release-monitor)
ANCHOR = "| `gitlab-release-monitor` |"


def apply(instance_dir: str) -> str:
    agents_path = os.path.join(instance_dir, "workspace", "AGENTS.md")
    if not os.path.exists(agents_path):
        return "AGENTS.md не найден — пропущено"

    with open(agents_path, "r", encoding="utf-8") as f:
        content = f.read()

    added = []
    for name, path, desc in NEW_SKILLS:
        if f"`{name}`" in content:
            continue
        row = f"| `{name}` | `{path}` | {desc} |"
        if ANCHOR in content:
            content = content.replace(ANCHOR, ANCHOR + "\n" + row, 1)
        elif "## Инструменты" in content:
            content = content.replace("## Инструменты", row + "\n\n## Инструменты", 1)
        else:
            content += "\n" + row
        added.append(name)

    if not added:
        return "Все скиллы уже есть — пропущено"

    with open(agents_path, "w", encoding="utf-8") as f:
        f.write(content)

    return f"Добавлены скиллы: {', '.join(added)}"
