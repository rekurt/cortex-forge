#!/usr/bin/env python3
"""
Автообновление Anthropic OAuth токена для CortexForge.
Endpoint: https://api.anthropic.com/v1/oauth/token
Токен живёт 8 часов — обновляем за 1 час до истечения.
"""
import json, re, subprocess, urllib.request, urllib.error, pathlib, sys, time

TOKEN_FILE = pathlib.Path("/opt/cortex-forge/.anthropic_tokens.json")
COMPOSE    = "/opt/cortex-forge"
INSTANCES  = ["admin", "nikita", "dmitry", "vasily"]
SERVICES   = ["assistant-admin", "assistant-nikita", "assistant-dmitry", "assistant-vasily"]

ENDPOINT  = "https://api.anthropic.com/v1/oauth/token"
CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"

# Обновляем если < 3600 секунд (1 час) до истечения
REFRESH_THRESHOLD = 3600


def load():
    return json.loads(TOKEN_FILE.read_text())


def save(data):
    TOKEN_FILE.write_text(json.dumps(data, indent=2))
    TOKEN_FILE.chmod(0o600)


def needs_refresh(tokens):
    expires_ms = tokens.get("expiresAt", 0)
    remaining  = (expires_ms / 1000) - time.time()
    hours = remaining / 3600
    print(f"Токен истекает через {hours:.1f}ч")
    return remaining < REFRESH_THRESHOLD


def do_refresh(refresh_token):
    payload = json.dumps({
        "grant_type":    "refresh_token",
        "refresh_token": refresh_token,
        "client_id":     CLIENT_ID,
    }).encode()

    req = urllib.request.Request(
        ENDPOINT, data=payload,
        headers={
            "Content-Type":       "application/json",
            "anthropic-version":  "2023-06-01",
            "User-Agent":         "claude-code/2.1.63",
        },
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def update_env(new_token):
    paths = [pathlib.Path("/opt/cortex-forge/.env")] + [
        pathlib.Path(f"/opt/cortex-forge/instances/{n}/.env") for n in INSTANCES
    ]
    for p in paths:
        if not p.exists():
            continue
        c = p.read_text()
        c = re.sub(
            r"ANTHROPIC_API_KEY=sk-ant-[^\n]+",
            f"ANTHROPIC_API_KEY={new_token}",
            c
        )
        p.write_text(c)
    print("✅ Все .env обновлены")


def restart():
    subprocess.run(
        ["docker", "compose", "up", "-d"] + SERVICES,
        cwd=COMPOSE, check=True, capture_output=True
    )
    print("✅ Контейнеры перезапущены")


if __name__ == "__main__":
    tokens = load()

    force = "--force" in sys.argv
    if not force and not needs_refresh(tokens):
        print("Токен свежий, ничего делать не нужно")
        sys.exit(0)

    print("Обновляем токен...")
    try:
        result = do_refresh(tokens["refreshToken"])

        new_access  = result["access_token"]
        new_refresh = result.get("refresh_token", tokens["refreshToken"])
        expires_in  = result.get("expires_in", 28800)

        tokens["accessToken"]  = new_access
        tokens["refreshToken"] = new_refresh
        tokens["expiresAt"]    = int((time.time() + expires_in) * 1000)
        save(tokens)

        update_env(new_access)
        restart()

        hours = expires_in / 3600
        print(f"✅ Токен обновлён, истекает через {hours:.0f}ч")

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        sys.exit(1)
