"""Удалить CLAUDE_AI_SESSION_KEY из openclaw.json всех инстансов — это поле хрупкое и конфликтует с auth-profiles.json."""
import pathlib
import json

DESCRIPTION = "remove CLAUDE_AI_SESSION_KEY from openclaw.json (conflicts with auth-profiles.json)"


def apply(workspace: pathlib.Path):
    # openclaw.json живёт рядом с workspace: instances/<name>/openclaw_data/openclaw.json
    openclaw_json = workspace.parent / "openclaw.json"
    if not openclaw_json.exists():
        return "openclaw.json не найден — пропускаем"

    data = json.loads(openclaw_json.read_text())

    env_vars = data.get("env", {}).get("vars", {})
    if "CLAUDE_AI_SESSION_KEY" not in env_vars:
        return "CLAUDE_AI_SESSION_KEY уже отсутствует — ок"

    del env_vars["CLAUDE_AI_SESSION_KEY"]

    # Убедимся что структура сохранена
    if "env" in data and "vars" in data["env"]:
        data["env"]["vars"] = env_vars

    openclaw_json.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    return "CLAUDE_AI_SESSION_KEY удалён из openclaw.json ✓"
