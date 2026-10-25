#!/usr/bin/env python3
"""
Bulk Provisioning & Fleet Management CLI (ENT1K-2) for CortexForge.

Supports onboarding and managing up to 1,000+ isolated Hermes Agent instances
with atomic .env updates, compose shard profiles, port collision prevention,
and symlink-safe template copying. Python 3.12+ stdlib only.
"""
from __future__ import annotations

import argparse
import csv
import fcntl
import json
import os
import pathlib
import re
import secrets
import shutil
import stat
import sys
import tempfile
from dataclasses import dataclass
from typing import Any

NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{1,31}$")
BOT_TOKEN_RE = re.compile(r"^[0-9]+:[A-Za-z0-9_-]+$")
TG_ID_RE = re.compile(r"^[0-9]+(?:,[0-9]+)*$")
DEPT_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
PORT_MAPPING_RE = re.compile(r'127\.0\.0\.1:(\d+):9119')
SERVICE_HEADER_RE = re.compile(r"^  assistant-([a-z0-9_-]+):\s*$", re.MULTILINE)


@dataclass(frozen=True)
class UserSpec:
    name: str
    bot_token: str
    full_name: str
    tg_id: str
    department: str = ""
    quota_limit: int = 1_000_000
    ui_port: int | None = None


def _ensure_not_symlink(path: pathlib.Path, description: str = "path") -> None:
    if path.is_symlink():
        raise ValueError(f"Symlink rejected for {description}: {path}")


def _verify_tree_no_symlinks(root: pathlib.Path) -> None:
    _ensure_not_symlink(root, "template root")
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        base = pathlib.Path(dirpath)
        for d in dirnames:
            _ensure_not_symlink(base / d, "template directory")
        for f in filenames:
            _ensure_not_symlink(base / f, "template file")


def _safe_copy_file(src: pathlib.Path, dst: pathlib.Path, mode: int | None = None) -> None:
    _ensure_not_symlink(src, "source file")
    if dst.exists() or dst.is_symlink():
        _ensure_not_symlink(dst, "destination file")
    shutil.copy2(src, dst, follow_symlinks=False)
    if mode is not None:
        os.chmod(dst, mode)


def _safe_write_file(path: pathlib.Path, content: str, mode: int = 0o600) -> None:
    _ensure_not_symlink(path, "target file")
    parent = path.parent
    _ensure_not_symlink(parent, "parent directory")
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(parent))
    tmp_path = pathlib.Path(tmp_name)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


def _collect_migration_stems(root: pathlib.Path) -> list[str]:
    mig_dir = root / "migrations"
    if not mig_dir.is_dir():
        return []
    return sorted(p.stem for p in mig_dir.glob("[0-9]*.py") if p.is_file() and not p.is_symlink())


def _parse_env_file(path: pathlib.Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not path.is_file() or path.is_symlink():
        return result
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        val = v.strip()
        if " #" in val:
            val = val.split(" #", 1)[0].strip()
        result[k.strip()] = val
    return result


def _load_specs_from_file(file_path: pathlib.Path) -> list[dict[str, Any]]:
    _ensure_not_symlink(file_path, "input file")
    if not file_path.is_file():
        raise ValueError(f"Input file not found: {file_path}")

    suffix = file_path.suffix.lower()
    raw_text = file_path.read_text(encoding="utf-8")
    if suffix == ".json":
        data = json.loads(raw_text)
        if isinstance(data, dict) and "users" in data:
            data = data["users"]
        if not isinstance(data, list):
            raise ValueError("JSON input must be a list of user objects or {'users': [...]}")
        return data
    if suffix == ".csv":
        reader = csv.DictReader(raw_text.splitlines())
        return [dict(row) for row in reader]
    raise ValueError(f"Unsupported file format '{suffix}'. Use .csv or .json")


def _validate_and_normalize_specs(raw_rows: list[dict[str, Any]]) -> list[UserSpec]:
    if not raw_rows:
        raise ValueError("Input file contains no user records")

    specs: list[UserSpec] = []
    seen_names: set[str] = set()
    seen_env_suffixes: dict[str, str] = {}
    seen_ports: set[int] = set()

    for idx, row in enumerate(raw_rows, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"Record #{idx}: expected object/dict")

        name = str(row.get("name") or "").strip()
        if name == "admin":
            raise ValueError(f"Record #{idx}: name 'admin' is reserved")
        if not NAME_RE.match(name):
            raise ValueError(
                f"Record #{idx}: invalid name '{name}' "
                "(expected ^[a-z][a-z0-9_-]{1,31}$)"
            )
        if name in seen_names:
            raise ValueError(f"Record #{idx}: duplicate user name '{name}' in batch")
        seen_names.add(name)

        env_suffix = name.upper().replace("-", "_")
        if env_suffix in seen_env_suffixes:
            raise ValueError(
                f"Record #{idx}: name '{name}' collides on normalized env suffix "
                f"'{env_suffix}' with '{seen_env_suffixes[env_suffix]}'"
            )
        seen_env_suffixes[env_suffix] = name

        bot_token = str(row.get("bot_token") or "").strip()
        if not bot_token or not BOT_TOKEN_RE.match(bot_token):
            raise ValueError(
                f"Record #{idx} ({name}): invalid bot_token (expected digits:alphanumeric)"
            )

        tg_id = str(row.get("tg_id") or "").strip()
        if not tg_id or not TG_ID_RE.match(tg_id):
            raise ValueError(
                f"Record #{idx} ({name}): invalid tg_id '{tg_id}' (expected numeric Telegram ID)"
            )

        full_name = str(row.get("full_name") or "").strip() or name
        if "\n" in full_name or "\r" in full_name:
            raise ValueError(f"Record #{idx} ({name}): full_name must not contain newlines")

        department = str(row.get("department") or "").strip()
        if department and not DEPT_RE.match(department):
            raise ValueError(
                f"Record #{idx} ({name}): invalid department '{department}'"
            )

        raw_quota = row.get("quota_limit")
        if raw_quota is None or str(raw_quota).strip() == "":
            quota_limit = 1_000_000
        else:
            try:
                quota_limit = int(str(raw_quota).strip())
            except ValueError as exc:
                raise ValueError(f"Record #{idx} ({name}): non-integer quota_limit") from exc
            if quota_limit <= 0:
                raise ValueError(f"Record #{idx} ({name}): quota_limit must be > 0")

        raw_port = row.get("ui_port")
        if raw_port is None or str(raw_port).strip() == "":
            ui_port = None
        else:
            try:
                ui_port = int(str(raw_port).strip())
            except ValueError as exc:
                raise ValueError(f"Record #{idx} ({name}): non-integer ui_port") from exc
            if ui_port < 1024 or ui_port > 65535 or ui_port == 18789:
                raise ValueError(
                    f"Record #{idx} ({name}): ui_port {ui_port} out of allowed range (1024-65535, != 18789)"
                )
            if ui_port in seen_ports:
                raise ValueError(
                    f"Record #{idx} ({name}): duplicate ui_port {ui_port} in batch"
                )
            seen_ports.add(ui_port)

        specs.append(
            UserSpec(
                name=name,
                bot_token=bot_token,
                full_name=full_name,
                tg_id=tg_id,
                department=department,
                quota_limit=quota_limit,
                ui_port=ui_port,
            )
        )

    return specs


def _parse_existing_override(override_path: pathlib.Path) -> tuple[dict[str, str], dict[str, int]]:
    """Return (service_blocks_by_user, port_by_user) from existing docker-compose.override.yml."""
    if not override_path.is_file():
        return {}, {}
    _ensure_not_symlink(override_path, "docker-compose.override.yml")
    text = override_path.read_text(encoding="utf-8")

    # Strip trailing top-level networks: block if present so we can regenerate cleanly
    net_marker = re.search(r"^networks:\s*$", text, re.MULTILINE)
    services_text = text[: net_marker.start()] if net_marker else text

    matches = list(SERVICE_HEADER_RE.finditer(services_text))
    blocks: dict[str, str] = {}
    ports: dict[str, int] = {}
    for i, m in enumerate(matches):
        uname = m.group(1)
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(services_text)
        block = services_text[start:end].rstrip()
        blocks[uname] = block
        pm = PORT_MAPPING_RE.search(block)
        if pm:
            ports[uname] = int(pm.group(1))
    return blocks, ports


def _render_service_block(
    name: str,
    ui_port: int,
    shard_id: int,
    department: str = "",
) -> str:
    name_upper = name.upper().replace("-", "_")
    shard_name = f"shard-{shard_id}"
    shard_net = f"corp-{shard_name}"
    dept_label = f"\n      corp.assistant.department: {department}" if department else ""
    return f"""  assistant-{name}:
    build:
      context: .
      dockerfile: instances/Dockerfile.user
    image: cortex-forge-user:latest
    container_name: corp-{name}
    restart: unless-stopped
    profiles:
      - "{shard_name}"
      - "all-users"
    env_file:
      - instances/{name}/.env
    volumes:
      - ./instances/{name}/hermes_data:/opt/data
      - ./instances/{name}/workspace:/opt/data/workspace
      - ./shared/skills:/shared/skills
      - ./shared/docs:/shared/docs
      - ./shared/compliance-data:/shared/compliance-data:ro
    environment:
      - ANTHROPIC_API_KEY=${{QUOTA_KEY_{name_upper}}}
      - OPENAI_API_KEY=${{OPENAI_API_KEY:-}}
      - SERVICE_API_KEY=${{SERVICE_API_KEY}}
      - BROKER_URL=http://message-broker:8080
      - BROKER_KEY=${{BROKER_KEY_{name_upper}}}
      - HERMES_UID=1000
      - HERMES_GID=1000
      - HERMES_DASHBOARD=1
    ports:
      - "127.0.0.1:{ui_port}:9119"
    networks:
      - corp-internal
      - corp-outbound
      - {shard_net}
    security_opt:
      - no-new-privileges:true
    deploy:
      resources:
        limits:
          cpus: "2.0"
          memory: 1G
    depends_on:
      quota-proxy:
        condition: service_healthy
      message-broker:
        condition: service_healthy
    labels:
      corp.assistant.role: personal
      corp.assistant.user: {name}
      corp.assistant.shard: {shard_name}{dept_label}"""


def _build_override_content(service_blocks: dict[str, str]) -> str:
    if not service_blocks:
        return "services: {}\n"

    shards_seen: set[int] = set()
    for block in service_blocks.values():
        for m in re.finditer(r"corp-shard-(\d+)", block):
            shards_seen.add(int(m.group(1)))

    lines = ["services:"]
    for uname in service_blocks:
        lines.append(service_blocks[uname])

    if shards_seen:
        lines.append("")
        lines.append("networks:")
        for sid in sorted(shards_seen):
            lines.append(f"  corp-shard-{sid}:")
            lines.append("    driver: bridge")
            lines.append("    internal: true")

    return "\n".join(lines) + "\n"


def _provision_instance_files(
    root: pathlib.Path,
    spec: UserSpec,
    broker_key: str,
    quota_key: str,
    gateway_token: str,
    migration_stems: list[str],
) -> None:
    template_dir = root / "instances" / "_template"
    template_ws = template_dir / "workspace"
    template_cfg = template_dir / "hermes_config.yaml.template"

    target_dir = root / "instances" / spec.name
    _ensure_not_symlink(target_dir, f"instance directory {spec.name}")
    target_ws = target_dir / "workspace"
    target_hermes = target_dir / "hermes_data"

    os.makedirs(target_hermes / "ssh", exist_ok=True)
    os.makedirs(target_ws / "skills", exist_ok=True)
    os.makedirs(target_ws / "memory", exist_ok=True)

    # Copy template workspace files/dirs (excluding memory/) without following symlinks
    for item in template_ws.iterdir():
        _ensure_not_symlink(item, "template workspace item")
        if item.name == "memory":
            continue
        dest = target_ws / item.name
        if item.is_dir():
            shutil.copytree(
                item,
                dest,
                symlinks=False,
                dirs_exist_ok=True,
                copy_function=lambda s, d: _safe_copy_file(pathlib.Path(s), pathlib.Path(d)),
            )
        elif item.is_file():
            _safe_copy_file(item, dest)

    # Substitute placeholders in USER.md, IDENTITY.md, SOUL.md
    for fname in ("USER.md", "IDENTITY.md", "SOUL.md"):
        fpath = target_ws / fname
        if fpath.is_file():
            _ensure_not_symlink(fpath, fname)
            text = fpath.read_text(encoding="utf-8")
            text = text.replace("{{FULL_NAME}}", spec.full_name).replace("{{NAME}}", spec.name)
            _safe_write_file(fpath, text, mode=0o644)

    # Record applied migrations so fresh instances don't re-run historical migrations
    applied_file = target_ws / ".migrations_applied"
    _safe_write_file(
        applied_file,
        ("\n".join(migration_stems) + "\n") if migration_stems else "",
        mode=0o644,
    )

    # Copy SOUL.md into hermes_data/SOUL.md with symlink protection
    soul_src = target_ws / "SOUL.md"
    soul_dst = target_hermes / "SOUL.md"
    if soul_src.is_file():
        _safe_copy_file(soul_src, soul_dst, mode=0o600)

    # Copy hermes_config.yaml.template -> hermes_data/config.yaml (0600)
    _safe_copy_file(template_cfg, target_hermes / "config.yaml", mode=0o600)

    # Create instances/<name>/.env (0600)
    dept_comment = f"# DEPARTMENT={spec.department}\n" if spec.department else ""
    instance_env = (
        f"# Instance secrets for {spec.name} — DO NOT commit to git!\n"
        f"{dept_comment}"
        f"BROKER_URL=http://message-broker:8080\n"
        f"BROKER_KEY={broker_key}\n"
    )
    _safe_write_file(target_dir / ".env", instance_env, mode=0o600)

    # Create instances/<name>/hermes_data/.env (0600)
    hermes_env = (
        f"# Hermes secrets for {spec.name} — DO NOT commit to git!\n"
        f"TELEGRAM_BOT_TOKEN={spec.bot_token}\n"
        f"TELEGRAM_ALLOWED_USERS={spec.tg_id}\n"
        f"HERMES_GATEWAY_TOKEN={gateway_token}\n"
        f"ANTHROPIC_API_KEY={quota_key}\n"
        f"# OPENAI_API_KEY=\n"
    )
    _safe_write_file(target_hermes / ".env", hermes_env, mode=0o600)


def _atomic_append_root_env(root_env: pathlib.Path, entries: list[str]) -> None:
    if not entries:
        return
    _ensure_not_symlink(root_env, "root .env")
    lock_path = root_env.parent / ".env.bulk.lock"
    with open(lock_path, "a", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            current = root_env.read_text(encoding="utf-8") if root_env.exists() else ""
            if current and not current.endswith("\n"):
                current += "\n"
            updated = current + "\n".join(entries) + "\n"
            _safe_write_file(root_env, updated, mode=0o600)
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def cmd_import(args: argparse.Namespace) -> int:
    root = pathlib.Path(args.root).resolve()
    if args.shard_size <= 0:
        print("❌ --shard-size must be >= 1", file=sys.stderr)
        return 1
    if args.base_port < 1024 or args.base_port > 65535 or args.base_port == 18789:
        print("❌ --base-port must be between 1024 and 65535 (excluding 18789)", file=sys.stderr)
        return 1

    root_env = root / ".env"
    if not root_env.is_file() or root_env.is_symlink():
        print(f"❌ Root .env not found or is a symlink: {root_env}", file=sys.stderr)
        return 1

    template_dir = root / "instances" / "_template"
    if not (template_dir / "workspace").is_dir() or not (template_dir / "hermes_config.yaml.template").is_file():
        print(f"❌ Template directory incomplete: {template_dir}", file=sys.stderr)
        return 1

    try:
        _verify_tree_no_symlinks(template_dir)
        raw_rows = _load_specs_from_file(pathlib.Path(args.file))
        specs = _validate_and_normalize_specs(raw_rows)
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"❌ Validation error: {exc}", file=sys.stderr)
        return 1

    instances_dir = root / "instances"
    os.makedirs(instances_dir, exist_ok=True)

    existing_env_suffixes: dict[str, str] = {}
    for d in sorted(instances_dir.iterdir(), key=lambda p: p.name):
        if not d.is_dir() or d.name in ("_template", "admin"):
            continue
        existing_env_suffixes[d.name.upper().replace("-", "_")] = d.name

    # Pre-check existing target directories for symlinks and normalized env-suffix collisions
    for spec in specs:
        candidate = instances_dir / spec.name
        if candidate.is_symlink():
            print(f"❌ Validation error: target instance path is a symlink: {candidate}", file=sys.stderr)
            return 1
        env_suffix = spec.name.upper().replace("-", "_")
        existing_name = existing_env_suffixes.get(env_suffix)
        if existing_name is not None and existing_name != spec.name:
            print(
                f"❌ Validation error: instance '{spec.name}' collides on normalized env suffix "
                f"'{env_suffix}' with existing instance '{existing_name}'",
                file=sys.stderr,
            )
            return 1

    override_path = root / "docker-compose.override.yml"
    try:
        service_blocks, existing_ports = _parse_existing_override(override_path)
    except ValueError as exc:
        print(f"❌ Override error: {exc}", file=sys.stderr)
        return 1

    used_ports: set[int] = set(existing_ports.values()) | {18789}
    # Reserve explicit ports from non-existing specs first and check collisions with existing ports
    for spec in specs:
        target_dir = instances_dir / spec.name
        if target_dir.exists():
            continue
        if spec.ui_port is not None:
            if spec.ui_port in used_ports:
                print(
                    f"❌ Port collision: ui_port {spec.ui_port} for '{spec.name}' is already in use",
                    file=sys.stderr,
                )
                return 1
            used_ports.add(spec.ui_port)

    next_port = args.base_port
    created: list[dict[str, Any]] = []
    skipped: list[str] = []
    env_lines_to_append: list[str] = []
    migration_stems = _collect_migration_stems(root)

    existing_user_count = len(service_blocks)

    for spec in specs:
        target_dir = instances_dir / spec.name
        if target_dir.exists():
            skipped.append(spec.name)
            continue

        if spec.ui_port is not None:
            port = spec.ui_port
        else:
            while next_port in used_ports:
                next_port += 1
            port = next_port
            used_ports.add(port)
            next_port += 1

        user_index = existing_user_count + len(created)
        shard_id = user_index // args.shard_size

        broker_key = secrets.token_urlsafe(32)
        quota_key = f"quota-{spec.name}-" + secrets.token_urlsafe(24)
        gateway_token = secrets.token_urlsafe(32)
        name_upper = spec.name.upper().replace("-", "_")

        if not args.dry_run:
            _provision_instance_files(
                root=root,
                spec=spec,
                broker_key=broker_key,
                quota_key=quota_key,
                gateway_token=gateway_token,
                migration_stems=migration_stems,
            )

        env_lines_to_append.extend(
            [
                f"BROKER_KEY_{name_upper}={broker_key}",
                f"QUOTA_KEY_{name_upper}={quota_key}",
                f"QUOTA_LIMIT_{name_upper}={spec.quota_limit}",
            ]
        )
        if spec.department:
            env_lines_to_append.append(f"QUOTA_DEPT_{name_upper}={spec.department}")
        service_blocks[spec.name] = _render_service_block(
            name=spec.name,
            ui_port=port,
            shard_id=shard_id,
            department=spec.department,
        )
        created.append(
            {
                "name": spec.name,
                "ui_port": port,
                "shard": f"shard-{shard_id}",
                "quota_limit": spec.quota_limit,
                "department": spec.department,
            }
        )

    if not args.dry_run and created:
        _atomic_append_root_env(root_env, env_lines_to_append)
        override_content = _build_override_content(service_blocks)
        _safe_write_file(override_path, override_content, mode=0o644)

    summary = {
        "dry_run": bool(args.dry_run),
        "created_count": len(created),
        "skipped_count": len(skipped),
        "shard_size": args.shard_size,
        "created": created,
        "skipped": skipped,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def _collect_fleet_records(root: pathlib.Path, include_secrets: bool = False) -> list[dict[str, Any]]:
    instances_dir = root / "instances"
    root_env = _parse_env_file(root / ".env")
    override_path = root / "docker-compose.override.yml"
    service_blocks, override_ports = _parse_existing_override(override_path)

    records: list[dict[str, Any]] = []
    if not instances_dir.is_dir():
        return records

    for d in sorted(instances_dir.iterdir(), key=lambda p: p.name):
        if not d.is_dir() or d.is_symlink() or d.name in ("_template", "admin"):
            continue
        name = d.name
        name_upper = name.upper().replace("-", "_")
        inst_env_path = d / ".env"
        hermes_env_path = d / "hermes_data" / ".env"
        hermes_cfg_path = d / "hermes_data" / "config.yaml"
        hermes_soul_path = d / "hermes_data" / "SOUL.md"
        ws_user_path = d / "workspace" / "USER.md"

        inst_env = _parse_env_file(inst_env_path)
        hermes_env = _parse_env_file(hermes_env_path)

        # Extract department comment if present
        department = ""
        if inst_env_path.is_file() and not inst_env_path.is_symlink():
            for line in inst_env_path.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("# DEPARTMENT="):
                    department = line.split("=", 1)[1].strip()
                    break

        full_name = name
        if ws_user_path.is_file() and not ws_user_path.is_symlink():
            m = re.search(r"^-\s*(?:Имя|Name):\s*(.+)$", ws_user_path.read_text(encoding="utf-8", errors="replace"), re.MULTILINE)
            if m:
                full_name = m.group(1).strip()

        block = service_blocks.get(name, "")
        shard = "unassigned"
        sm = re.search(r"corp\.assistant\.shard:\s*(shard-\d+)", block)
        if sm:
            shard = sm.group(1)
        else:
            pm = re.search(r'-\s*"(shard-\d+)"', block)
            if pm:
                shard = pm.group(1)

        raw_limit = root_env.get(f"QUOTA_LIMIT_{name_upper}", "1000000")
        try:
            quota_limit = int(raw_limit)
        except ValueError:
            quota_limit = 1_000_000

        checks = {
            "instance_env": inst_env_path.is_file() and not inst_env_path.is_symlink(),
            "hermes_env": hermes_env_path.is_file() and not hermes_env_path.is_symlink(),
            "hermes_config": hermes_cfg_path.is_file() and not hermes_cfg_path.is_symlink(),
            "hermes_soul": hermes_soul_path.is_file() and not hermes_soul_path.is_symlink(),
        }
        healthy = all(checks.values())

        rec: dict[str, Any] = {
            "name": name,
            "full_name": full_name,
            "tg_id": hermes_env.get("TELEGRAM_ALLOWED_USERS", ""),
            "department": department,
            "ui_port": override_ports.get(name),
            "shard": shard,
            "quota_limit": quota_limit,
            "healthy": healthy,
            "checks": checks,
        }
        if include_secrets:
            rec["secrets"] = {
                "bot_token": hermes_env.get("TELEGRAM_BOT_TOKEN", ""),
                "hermes_gateway_token": hermes_env.get("HERMES_GATEWAY_TOKEN", ""),
                "broker_key": inst_env.get("BROKER_KEY", root_env.get(f"BROKER_KEY_{name_upper}", "")),
                "quota_key": hermes_env.get("ANTHROPIC_API_KEY", root_env.get(f"QUOTA_KEY_{name_upper}", "")),
            }
        records.append(rec)

    return records


def cmd_export(args: argparse.Namespace) -> int:
    root = pathlib.Path(args.root).resolve()
    out_path = pathlib.Path(args.output)
    records = _collect_fleet_records(root, include_secrets=bool(args.include_secrets))
    payload = {
        "instance_count": len(records),
        "include_secrets": bool(args.include_secrets),
        "instances": records,
    }
    mode = 0o600 if args.include_secrets else 0o644
    os.makedirs(out_path.parent if out_path.parent != pathlib.Path("") else pathlib.Path("."), exist_ok=True)
    _safe_write_file(out_path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n", mode=mode)
    os.chmod(out_path, mode)
    print(json.dumps({"exported": len(records), "output": str(out_path)}, ensure_ascii=False))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    root = pathlib.Path(args.root).resolve()
    records = _collect_fleet_records(root, include_secrets=False)
    shards: dict[str, int] = {}
    healthy_count = 0
    degraded_instances: list[dict[str, Any]] = []
    ports_seen: dict[int, list[str]] = {}

    for rec in records:
        shard = rec["shard"]
        shards[shard] = shards.get(shard, 0) + 1
        if rec["healthy"]:
            healthy_count += 1
        else:
            missing = [k for k, ok in rec["checks"].items() if not ok]
            degraded_instances.append({"name": rec["name"], "missing": missing})
        port = rec.get("ui_port")
        if isinstance(port, int):
            ports_seen.setdefault(port, []).append(rec["name"])

    port_collisions = {str(p): names for p, names in ports_seen.items() if len(names) > 1}
    status_report = {
        "total_instances": len(records),
        "healthy_instances": healthy_count,
        "degraded_instances": len(degraded_instances),
        "shards": shards,
        "port_collisions": port_collisions,
        "degraded_details": degraded_instances,
    }
    print(json.dumps(status_report, ensure_ascii=False, indent=2))
    return 0 if not degraded_instances and not port_collisions else 1


def build_parser() -> argparse.ArgumentParser:
    default_root = pathlib.Path.cwd()
    if not (default_root / "instances").exists():
        default_root = pathlib.Path(__file__).resolve().parent.parent

    parser = argparse.ArgumentParser(
        prog="bulk-users.py",
        description="Bulk user provisioning & fleet management for CortexForge (1000+ instances)",
    )
    parser.add_argument(
        "--root",
        default=str(default_root),
        help="Repository root directory (default: current directory or repo root)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_import = sub.add_parser("import", help="Bulk import users from CSV or JSON")
    p_import.add_argument("--file", required=True, help="Path to users.csv or users.json")
    p_import.add_argument("--dry-run", action="store_true", help="Validate and preview without writing files")
    p_import.add_argument("--shard-size", type=int, default=100, help="Instances per compose profile shard (default: 100)")
    p_import.add_argument("--base-port", type=int, default=18790, help="Starting localhost dashboard port (default: 18790)")
    p_import.add_argument("--root", default=argparse.SUPPRESS, help="Repository root directory")
    p_import.set_defaults(func=cmd_import)

    p_export = sub.add_parser("export", help="Export fleet metadata manifest to JSON")
    p_export.add_argument("--output", required=True, help="Output manifest JSON file path")
    p_export.add_argument("--include-secrets", action="store_true", help="Include secret tokens (writes 0600 file)")
    p_export.add_argument("--root", default=argparse.SUPPRESS, help="Repository root directory")
    p_export.set_defaults(func=cmd_export)

    p_status = sub.add_parser("status", help="Inspect fleet health, shard distribution, and file integrity")
    p_status.add_argument("--root", default=argparse.SUPPRESS, help="Repository root directory")
    p_status.set_defaults(func=cmd_status)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
