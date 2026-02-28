#!/usr/bin/env python3
"""
Обновляет Anthropic OAuth токен через refreshToken и перезапускает контейнеры.
Запускается кроном за 7 дней до истечения.
"""
import json, re, subprocess, urllib.request, urllib.error, pathlib, sys, time

TOKEN_FILE = pathlib.Path("/opt/cortex-forge/.anthropic_tokens.json")
ENV_FILE   = pathlib.Path("/opt/cortex-forge/.env")
INSTANCES  = ["admin", "nikita", "dmitry", "vasily"]
SERVICES   = ["assistant-admin", "assistant-nikita", "assistant-dmitry", "assistant-vasily"]
COMPOSE    = "/opt/cortex-forge"

def load_tokens():
    return json.loads(TOKEN_FILE.read_text())

def save_tokens(data):
    TOKEN_FILE.write_text(json.dumps(data, indent=2))
    TOKEN_FILE.chmod(0o600)

def token_expires_soon(tokens, days=7):
    expires_ms = tokens.get("expiresAt", 0)
    remaining  = (expires_ms / 1000) - time.time()
    print(f"Токен истекает через {remaining/86400:.1f} дней")
    return remaining < days * 86400

def refresh(tokens):
    refresh_token = tokens["refreshToken"]
    # Пробуем несколько возможных endpoint-ов
    endpoints = [
        "https://claude.ai/api/auth/oauth/token",
        "https://api.anthropic.com/oauth/token",
    ]
    payload = json.dumps({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }).encode()

    for url in endpoints:
        try:
            req = urllib.request.Request(url, data=payload,
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.loads(r.read())
                print(f"Refreshed via {url}")
                return data
        except Exception as e:
            print(f"  {url}: {e}")
    raise RuntimeError("Все endpoint-ы не ответили")

def update_env(new_token):
    for path in [ENV_FILE] + [
        pathlib.Path(f"/opt/cortex-forge/instances/{n}/.env") for n in INSTANCES
    ]:
        if not path.exists():
            continue
        content = path.read_text()
        content = re.sub(
            r"ANTHROPIC_API_KEY=sk-ant-[^\n]+",
            f"ANTHROPIC_API_KEY={new_token}",
            content
        )
        path.write_text(content)
    print("Все .env обновлены")

def restart_containers():
    subprocess.run(
        ["docker", "compose", "up", "-d"] + SERVICES,
        cwd=COMPOSE, check=True, capture_output=True
    )
    print("Контейнеры перезапущены")

if __name__ == "__main__":
    tokens = load_tokens()

    force = "--force" in sys.argv
    if not force and not token_expires_soon(tokens):
        print("Токен ещё свежий, ничего делать не нужно")
        sys.exit(0)

    print("Обновляем токен...")
    try:
        result = refresh(tokens)
        new_access  = result.get("access_token") or result.get("accessToken")
        new_refresh = result.get("refresh_token") or result.get("refreshToken")
        new_expires = result.get("expires_in") and (time.time() + result["expires_in"]) * 1000 \
                      or result.get("expiresAt")

        if new_access:
            tokens["accessToken"]  = new_access
            tokens["refreshToken"] = new_refresh or tokens["refreshToken"]
            tokens["expiresAt"]    = new_expires or tokens["expiresAt"]
            save_tokens(tokens)
            update_env(new_access)
            restart_containers()
            print("Готово!")
        else:
            print("Ответ не содержит нового токена:", result)
            sys.exit(1)
    except Exception as e:
        print(f"Ошибка: {e}")
        sys.exit(1)
