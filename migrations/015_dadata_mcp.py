"""Добавить DaData MCP сервер в openclaw.json всех инстансов."""
import pathlib, json

DESCRIPTION = "add DaData MCP to all instances — address/company lookup"

MCP_BLOCK = {
    "dadata": {
        "command": "npx",
        "args": [
            "-y",
            "supergateway",
            "--streamableHttp",
            "https://mcp.dadata.ru/mcp",
            "--oauth2Bearer",
            "${DADATA_API_KEY}:${DADATA_SECRET}"
        ]
    }
}


def apply(workspace: pathlib.Path):
    cfg_path = workspace.parent / "openclaw.json"
    if not cfg_path.exists():
        return "пропущен — нет openclaw.json"

    try:
        data = json.loads(cfg_path.read_text())
    except json.JSONDecodeError:
        return "пропущен — невалидный JSON"

    mcp = data.setdefault("mcpServers", {})
    if "dadata" in mcp:
        return "уже есть"

    mcp["dadata"] = MCP_BLOCK["dadata"]
    cfg_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return "DaData MCP добавлен"
