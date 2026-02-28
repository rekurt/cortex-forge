"""Удалить mcpServers из openclaw.json всех инстансов.
mcpServers не поддерживается в текущей версии OpenClaw на этих инстансах."""
import pathlib, json

DESCRIPTION = "remove mcpServers from openclaw.json — not supported in current version"


def apply(workspace: pathlib.Path):
    cfg = workspace.parent / "openclaw.json"
    if not cfg.exists():
        return "нет openclaw.json"
    data = json.loads(cfg.read_text())
    if "mcpServers" not in data:
        return "уже чисто"
    del data["mcpServers"]
    cfg.write_text(json.dumps(data, indent=2))
    return "mcpServers удалён из openclaw.json"
