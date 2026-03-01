#!/usr/bin/env python3
"""
Применяет новые миграции воркспейса ко всем существующим инстансам.
Запускается автоматически из post-merge хука.
Использование: python3 scripts/migrate-instances.py [--dry-run]
"""
import sys
import importlib.util
import pathlib

REPO_ROOT   = pathlib.Path(__file__).parent.parent
OVERRIDES   = REPO_ROOT.parent / "overrides"

def _collect_migrations():
    engine_migs = {p.stem: p for p in (REPO_ROOT / "migrations").glob("[0-9]*.py")}
    if (OVERRIDES / "migrations").exists():
        for p in (OVERRIDES / "migrations").glob("[0-9]*.py"):
            engine_migs[p.stem] = p  # overrides приоритетнее engine
    return sorted(engine_migs.values(), key=lambda p: p.stem)

MIGRATIONS  = _collect_migrations()
INSTANCES   = REPO_ROOT / "instances"
APPLIED_FILE = ".migrations_applied"
DRY_RUN = "--dry-run" in sys.argv

def load_migration(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def get_applied(workspace):
    f = workspace / APPLIED_FILE
    if not f.exists():
        return set()
    return set(l.strip() for l in f.read_text().splitlines() if l.strip())

def mark_applied(workspace, migration_id):
    f = workspace / APPLIED_FILE
    applied = get_applied(workspace)
    applied.add(migration_id)
    f.write_text("\n".join(sorted(applied)) + "\n")

def run():
    updated = []

    if not MIGRATIONS:
        print("  Нет миграций.")
        return updated

    instances = [
        d for d in INSTANCES.iterdir()
        if d.is_dir()
        and d.name not in ("_template",)
        and (d / "openclaw_data" / "workspace").exists()
    ]

    if not instances:
        print("  Нет инстансов для обновления.")
        return updated

    for instance_dir in sorted(instances):
        workspace = instance_dir / "openclaw_data" / "workspace"
        applied   = get_applied(workspace)
        pending   = [m for m in MIGRATIONS if m.stem not in applied]

        if not pending:
            print(f"  [{instance_dir.name}] актуален")
            continue

        print(f"  [{instance_dir.name}] применяю {len(pending)} миграций:")
        instance_updated = False
        for mig_path in pending:
            mod = load_migration(mig_path)
            mid = mig_path.stem
            desc = getattr(mod, "DESCRIPTION", mid)
            try:
                if DRY_RUN:
                    print(f"    [dry] {mid}: {desc}")
                else:
                    mod.apply(workspace)
                    mark_applied(workspace, mid)
                    print(f"    ✅ {mid}: {desc}")
                    instance_updated = True
            except Exception as e:
                print(f"    ❌ {mid}: {e}")
        if instance_updated:
            updated.append(instance_dir.name)
            # Сбрасываем кеш сессий — иначе агент продолжит работать
            # со старым SOUL.md/AGENTS.md из закешированной истории
            sessions_dir = instance_dir / "openclaw_data" / "agents" / "main" / "sessions"
            if sessions_dir.exists() and not DRY_RUN:
                for f in sessions_dir.glob("*.jsonl"):
                    f.unlink()
                sess_json = sessions_dir / "sessions.json"
                if sess_json.exists():
                    sess_json.unlink()
                print(f"  [{instance_dir.name}] 🗑️  сессии сброшены")

    return updated

if __name__ == "__main__":
    updated = run()
    if updated:
        # Выводим машиночитаемую строку для хука
        print(f"MIGRATED_INSTANCES: {' '.join(updated)}")
