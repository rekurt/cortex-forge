"""
Migration 023: Добавить gitlab-release-monitor в таблицу скиллов AGENTS.md
"""

MIGRATION_ID = "023_add_gitlab_monitor_skill"

import os

NEW_ROW = "| `gitlab-release-monitor` | `/shared/skills/gitlab-release-monitor/` | Мониторинг новых тегов/релизов в GitLab-репозиториях — уведомления в Telegram |"

def apply(instance_dir: str) -> str:
    workspace = os.path.join(instance_dir, "workspace")
    agents_path = os.path.join(workspace, "AGENTS.md")

    if not os.path.exists(agents_path):
        return "AGENTS.md не найден — пропущено"

    with open(agents_path, "r", encoding="utf-8") as f:
        content = f.read()

    if "gitlab-release-monitor" in content:
        return "gitlab-release-monitor уже есть — пропущено"

    # Вставляем после последней строки таблицы скиллов (после yandex-oauth)
    anchor = "| `yandex-oauth` |"
    if anchor in content:
        content = content.replace(anchor, NEW_ROW + "\n" + anchor)
    else:
        # fallback: добавить перед ## Инструменты или в конец таблицы
        if "## Инструменты" in content:
            content = content.replace("## Инструменты", NEW_ROW + "\n\n## Инструменты")
        else:
            content += "\n" + NEW_ROW

    with open(agents_path, "w", encoding="utf-8") as f:
        f.write(content)

    return "gitlab-release-monitor добавлен в таблицу скиллов"
