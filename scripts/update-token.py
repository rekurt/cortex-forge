#!/usr/bin/env python3
"""Ротация OAuth токена во всех инстансах Capuchin.

Обновляет auth-profiles.json напрямую (правильное хранилище),
не трогает openclaw.json.

Использование:
    python3 scripts/update-token.py --token sk-ant-oat01-XXX
    python3 scripts/update-token.py --token sk-ant-oat01-XXX --restart
    python3 scripts/update-token.py --token sk-ant-oat01-XXX --instance admin
"""
import argparse
import json
import pathlib
import subprocess
import sys

INSTANCES_DIR = pathlib.Path(__file__).parent.parent / "instances"
AUTH_PROFILE_REL = pathlib.Path("openclaw_data/agents/main/agent/auth-profiles.json")

AUTH_PROFILE_TEMPLATE = {
    "version": 1,
    "profiles": {
        "anthropic:default": {
            "type": "token",
            "provider": "anthropic",
            "token": "",
        }
    },
    "lastGood": {"anthropic": "anthropic:default"},
}


def update_instance(name: str, token: str) -> str:
    inst_dir = INSTANCES_DIR / name
    if not inst_dir.exists():
        return f"{name}: директория не найдена — пропущено"

    auth_path = inst_dir / AUTH_PROFILE_REL
    auth_path.parent.mkdir(parents=True, exist_ok=True)

    # Читаем существующий профиль или создаём с нуля
    if auth_path.exists():
        try:
            data = json.loads(auth_path.read_text())
        except json.JSONDecodeError:
            data = json.loads(json.dumps(AUTH_PROFILE_TEMPLATE))
    else:
        data = json.loads(json.dumps(AUTH_PROFILE_TEMPLATE))

    # Обновляем токен
    data.setdefault("profiles", {}).setdefault("anthropic:default", {})["token"] = token
    data.setdefault("lastGood", {})["anthropic"] = "anthropic:default"

    # Сбрасываем счётчик ошибок чтобы OpenClaw не считал профиль битым
    if "usageStats" in data and "anthropic:default" in data["usageStats"]:
        data["usageStats"]["anthropic:default"]["errorCount"] = 0

    auth_path.write_text(json.dumps(data, indent=2) + "\n")
    return f"{name}: токен обновлён → {auth_path}"


def restart_instance(name: str, compose_dir: pathlib.Path) -> str:
    service = f"assistant-{name}"
    result = subprocess.run(
        ["docker", "compose", "restart", service],
        cwd=compose_dir,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return f"{name}: контейнер перезапущен"
    else:
        return f"{name}: ошибка рестарта — {result.stderr.strip()}"


def main():
    parser = argparse.ArgumentParser(description="Обновить OAuth токен во всех инстансах Capuchin")
    parser.add_argument("--token", required=True, help="Новый OAuth токен (sk-ant-oat01-...)")
    parser.add_argument("--instance", help="Конкретный инстанс (по умолчанию — все)")
    parser.add_argument("--restart", action="store_true", help="Перезапустить контейнеры после обновления")
    args = parser.parse_args()

    if not args.token.startswith("sk-ant-oat01-"):
        print(f"⚠️  Токен не похож на OAuth: {args.token[:20]}...", file=sys.stderr)
        print("Ожидается формат sk-ant-oat01-...", file=sys.stderr)
        sys.exit(1)

    # Определяем инстансы
    if args.instance:
        instances = [args.instance]
    else:
        instances = sorted(
            d.name for d in INSTANCES_DIR.iterdir()
            if d.is_dir() and not d.name.startswith("_") and not d.name.startswith(".")
        )

    compose_dir = INSTANCES_DIR.parent  # engine/

    print(f"Токен: {args.token[:25]}...{args.token[-6:]}")
    print(f"Инстансы: {', '.join(instances)}")
    print()

    for name in instances:
        msg = update_instance(name, args.token)
        print(f"  ✓ {msg}")

    if args.restart:
        print()
        print("Перезапуск контейнеров...")
        for name in instances:
            msg = restart_instance(name, compose_dir)
            print(f"  {msg}")

    print()
    print("Готово. Если не передавал --restart — запусти:")
    print(f"  docker compose -f {compose_dir}/docker-compose.yml restart {' '.join('assistant-' + n for n in instances)}")


if __name__ == "__main__":
    main()
