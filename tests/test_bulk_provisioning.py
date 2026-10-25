#!/usr/bin/env python3
"""
Tests for ENT1K-2 Bulk Provisioning & Fleet Management (scripts/bulk-users.py).
"""
from __future__ import annotations

import csv
import importlib.util
import io
import json
import os
import pathlib
import shutil
import stat
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "bulk-users.py"


def _load_bulk_module():
    spec = importlib.util.spec_from_file_location("bulk_users", SCRIPT_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bulk_users = _load_bulk_module()


class TestBulkProvisioning(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = pathlib.Path(tempfile.mkdtemp(prefix="cortex-bulk-test-"))
        # Prepare minimal repo layout with real template files
        tpl_src = REPO_ROOT / "instances" / "_template"
        tpl_dst = self.tmp_dir / "instances" / "_template"
        shutil.copytree(tpl_src, tpl_dst, symlinks=False)

        mig_dir = self.tmp_dir / "migrations"
        mig_dir.mkdir(parents=True, exist_ok=True)
        (mig_dir / "001_init.py").write_text("DESCRIPTION = 'init'\n", encoding="utf-8")
        (mig_dir / "024_latest.py").write_text("DESCRIPTION = 'latest'\n", encoding="utf-8")

        root_env = self.tmp_dir / ".env"
        root_env.write_text(
            "ANTHROPIC_API_KEY=sk-ant-test-key\n"
            "QUOTA_ADMIN_TOKEN=admin-test-token-0123456789abcdef\n",
            encoding="utf-8",
        )
        os.chmod(root_env, 0o600)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _run_cli(self, argv: list[str]) -> tuple[int, str, str]:
        out_buf = io.StringIO()
        err_buf = io.StringIO()
        with redirect_stdout(out_buf), redirect_stderr(err_buf):
            rc = bulk_users.main(["--root", str(self.tmp_dir), *argv])
        return rc, out_buf.getvalue(), err_buf.getvalue()

    def test_bulk_import_120_users_sharding_and_ports(self) -> None:
        """Import 120 users in one call; verify speed, shards, ports, and 0600 files."""
        csv_path = self.tmp_dir / "users_120.csv"
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["name", "bot_token", "full_name", "tg_id", "department", "quota_limit"],
            )
            writer.writeheader()
            for i in range(1, 121):
                writer.writerow(
                    {
                        "name": f"emp-{i:04d}",
                        "bot_token": f"700{i:04d}:AAtestBotToken_{i:04d}",
                        "full_name": f"Employee #{i}",
                        "tg_id": str(1000000 + i),
                        "department": "eng" if i <= 60 else "ops",
                        "quota_limit": str(500_000 if i % 2 == 0 else 1_000_000),
                    }
                )

        t0 = time.monotonic()
        rc, out, err = self._run_cli(
            ["import", "--file", str(csv_path), "--shard-size", "50", "--base-port", "18790"]
        )
        elapsed = time.monotonic() - t0
        self.assertEqual(rc, 0, f"Unexpected stderr: {err}")
        self.assertLess(elapsed, 10.0, f"Bulk import of 120 users took too long: {elapsed:.2f}s")

        summary = json.loads(out)
        self.assertEqual(summary["created_count"], 120)
        self.assertEqual(summary["skipped_count"], 0)

        # Verify unique ports 18790..18909
        ports = [item["ui_port"] for item in summary["created"]]
        self.assertEqual(len(ports), len(set(ports)))
        self.assertEqual(ports[0], 18790)
        self.assertEqual(ports[-1], 18909)

        # Verify shard distribution (50 per shard -> shard-0: 50, shard-1: 50, shard-2: 20)
        shards = [item["shard"] for item in summary["created"]]
        self.assertEqual(shards.count("shard-0"), 50)
        self.assertEqual(shards.count("shard-1"), 50)
        self.assertEqual(shards.count("shard-2"), 20)

        # Spot-check instance files and permissions
        sample_dir = self.tmp_dir / "instances" / "emp-0001"
        self.assertTrue((sample_dir / "hermes_data" / "ssh").is_dir())
        self.assertTrue((sample_dir / "workspace" / "skills").is_dir())
        self.assertTrue((sample_dir / "workspace" / "memory").is_dir())

        for rel in (".env", "hermes_data/.env", "hermes_data/config.yaml", "hermes_data/SOUL.md"):
            p = sample_dir / rel
            self.assertTrue(p.is_file(), f"Missing {rel}")
            mode = stat.S_IMODE(p.stat().st_mode)
            self.assertEqual(mode, 0o600, f"Expected 0600 on {rel}, got {oct(mode)}")

        user_md = (sample_dir / "workspace" / "USER.md").read_text(encoding="utf-8")
        self.assertIn("Employee #1", user_md)
        self.assertNotIn("{{FULL_NAME}}", user_md)

        migs = (sample_dir / "workspace" / ".migrations_applied").read_text(encoding="utf-8").splitlines()
        self.assertEqual(migs, ["001_init", "024_latest"])

        # Verify root .env has all 120 users' keys and 0600 permissions
        root_env_path = self.tmp_dir / ".env"
        self.assertEqual(stat.S_IMODE(root_env_path.stat().st_mode), 0o600)
        root_env_text = root_env_path.read_text(encoding="utf-8")
        self.assertIn("BROKER_KEY_EMP_0001=", root_env_text)
        self.assertIn("QUOTA_KEY_EMP_0120=quota-emp-0120-", root_env_text)
        self.assertIn("QUOTA_LIMIT_EMP_0002=500000", root_env_text)
        self.assertIn("QUOTA_DEPT_EMP_0001=eng", root_env_text)
        self.assertIn("QUOTA_DEPT_EMP_0120=ops", root_env_text)

        # Verify docker-compose.override.yml contains shard profiles and shard bridge networks
        override_text = (self.tmp_dir / "docker-compose.override.yml").read_text(encoding="utf-8")
        self.assertIn("assistant-emp-0001:", override_text)
        self.assertIn("assistant-emp-0120:", override_text)
        self.assertIn('- "shard-0"', override_text)
        self.assertIn('- "shard-1"', override_text)
        self.assertIn('- "shard-2"', override_text)
        self.assertIn("corp-shard-0:", override_text)
        self.assertIn("corp-shard-1:", override_text)
        self.assertIn("corp-shard-2:", override_text)

    def test_idempotency_and_incremental_import(self) -> None:
        """Re-importing existing users skips them safely while adding new ones."""
        batch1 = [
            {"name": "user-a", "bot_token": "701:AAtokenA", "full_name": "User A", "tg_id": "111"},
            {"name": "user-b", "bot_token": "702:AAtokenB", "full_name": "User B", "tg_id": "222"},
        ]
        json_path = self.tmp_dir / "batch.json"
        json_path.write_text(json.dumps(batch1), encoding="utf-8")

        rc1, out1, _ = self._run_cli(["import", "--file", str(json_path)])
        self.assertEqual(rc1, 0)
        self.assertEqual(json.loads(out1)["created_count"], 2)

        orig_env_a = (self.tmp_dir / "instances" / "user-a" / "hermes_data" / ".env").read_text(encoding="utf-8")

        batch2 = batch1 + [
            {"name": "user-c", "bot_token": "703:AAtokenC", "full_name": "User C", "tg_id": "333"},
        ]
        json_path.write_text(json.dumps({"users": batch2}), encoding="utf-8")

        rc2, out2, _ = self._run_cli(["import", "--file", str(json_path)])
        self.assertEqual(rc2, 0)
        res2 = json.loads(out2)
        self.assertEqual(res2["created_count"], 1)
        self.assertEqual(res2["skipped"], ["user-a", "user-b"])
        self.assertEqual(res2["created"][0]["name"], "user-c")
        self.assertEqual(res2["created"][0]["ui_port"], 18792)

        # Ensure user-a secrets were not overwritten
        after_env_a = (self.tmp_dir / "instances" / "user-a" / "hermes_data" / ".env").read_text(encoding="utf-8")
        self.assertEqual(orig_env_a, after_env_a)

    def test_status_and_export_commands(self) -> None:
        """Verify status integrity checks and export secret redaction / 0600 mode."""
        users = [
            {
                "name": "alice-1",
                "bot_token": "801:AAaliceSecret",
                "full_name": "Alice One",
                "tg_id": "9001",
                "department": "finance",
                "quota_limit": 750000,
            },
            {
                "name": "bob-2",
                "bot_token": "802:AAbobSecret",
                "full_name": "Bob Two",
                "tg_id": "9002",
                "department": "legal",
                "quota_limit": 1250000,
            },
        ]
        src_file = self.tmp_dir / "users.json"
        src_file.write_text(json.dumps(users), encoding="utf-8")
        self.assertEqual(self._run_cli(["import", "--file", str(src_file), "--shard-size", "1"])[0], 0)

        # Status when healthy
        rc_st, out_st, _ = self._run_cli(["status"])
        self.assertEqual(rc_st, 0)
        status_data = json.loads(out_st)
        self.assertEqual(status_data["total_instances"], 2)
        self.assertEqual(status_data["healthy_instances"], 2)
        self.assertEqual(status_data["shards"], {"shard-0": 1, "shard-1": 1})

        # Export without secrets
        manifest_pub = self.tmp_dir / "manifest-public.json"
        rc_ex, _, _ = self._run_cli(["export", "--output", str(manifest_pub)])
        self.assertEqual(rc_ex, 0)
        pub_data = json.loads(manifest_pub.read_text(encoding="utf-8"))
        self.assertEqual(pub_data["instance_count"], 2)
        self.assertNotIn("secrets", pub_data["instances"][0])
        self.assertNotIn("AAaliceSecret", manifest_pub.read_text(encoding="utf-8"))

        # Export with secrets (must have 0600 permissions)
        manifest_sec = self.tmp_dir / "manifest-secret.json"
        rc_ex_sec, _, _ = self._run_cli(["export", "--output", str(manifest_sec), "--include-secrets"])
        self.assertEqual(rc_ex_sec, 0)
        self.assertEqual(stat.S_IMODE(manifest_sec.stat().st_mode), 0o600)
        sec_data = json.loads(manifest_sec.read_text(encoding="utf-8"))
        self.assertEqual(sec_data["instances"][0]["secrets"]["bot_token"], "801:AAaliceSecret")

        # Break one file and verify status returns non-zero and flags degraded instance
        (self.tmp_dir / "instances" / "bob-2" / "hermes_data" / "config.yaml").unlink()
        rc_deg, out_deg, _ = self._run_cli(["status"])
        self.assertEqual(rc_deg, 1)
        deg_data = json.loads(out_deg)
        self.assertEqual(deg_data["degraded_instances"], 1)
        self.assertEqual(deg_data["degraded_details"][0]["name"], "bob-2")
        self.assertIn("hermes_config", deg_data["degraded_details"][0]["missing"])

    def test_rejects_invalid_records_and_symlinks(self) -> None:
        """Invalid records or symlinks must be rejected before modifying state."""
        invalid_batches = [
            [{"name": "admin", "bot_token": "123:AAok", "full_name": "Admin", "tg_id": "111"}],
            [{"name": "../evil", "bot_token": "123:AAok", "full_name": "Evil", "tg_id": "111"}],
            [{"name": "UpperCase", "bot_token": "123:AAok", "full_name": "Bad", "tg_id": "111"}],
            [{"name": "valid-1", "bot_token": "not-a-token", "full_name": "Bad Tok", "tg_id": "111"}],
            [{"name": "valid-1", "bot_token": "123:AAok", "full_name": "Bad TG", "tg_id": "abc"}],
            [{"name": "valid-1", "bot_token": "123:AAok", "full_name": "Port 18789", "tg_id": "111", "ui_port": 18789}],
            [
                {"name": "user-1", "bot_token": "123:AAok1", "full_name": "U1", "tg_id": "111"},
                {"name": "user_1", "bot_token": "124:AAok2", "full_name": "U2", "tg_id": "222"},
            ],
        ]
        bad_file = self.tmp_dir / "bad.json"
        for batch in invalid_batches:
            bad_file.write_text(json.dumps(batch), encoding="utf-8")
            rc, _, err = self._run_cli(["import", "--file", str(bad_file)])
            self.assertNotEqual(rc, 0, f"Batch should have failed: {batch}")
            self.assertIn("Validation error", err)

        # Collision with an already-existing instance directory on normalized env suffix (user-1 vs user_1)
        first_file = self.tmp_dir / "first_u1.json"
        first_file.write_text(
            json.dumps([{"name": "user-1", "bot_token": "123:AAok1", "full_name": "U1", "tg_id": "111"}]),
            encoding="utf-8",
        )
        self.assertEqual(self._run_cli(["import", "--file", str(first_file)])[0], 0)

        second_file = self.tmp_dir / "second_u1.json"
        second_file.write_text(
            json.dumps([{"name": "user_1", "bot_token": "124:AAok2", "full_name": "U2", "tg_id": "222"}]),
            encoding="utf-8",
        )
        rc_col, _, err_col = self._run_cli(["import", "--file", str(second_file)])
        self.assertNotEqual(rc_col, 0)
        self.assertIn("collides on normalized env suffix", err_col)

        # Symlink attack inside template workspace must be rejected
        good_file = self.tmp_dir / "good.json"
        good_file.write_text(
            json.dumps([{"name": "safe-user", "bot_token": "123:AAok", "full_name": "Safe", "tg_id": "111"}]),
            encoding="utf-8",
        )
        symlink_in_tpl = self.tmp_dir / "instances" / "_template" / "workspace" / "evil_link.md"
        symlink_in_tpl.symlink_to("/etc/passwd")
        try:
            rc_sym, _, err_sym = self._run_cli(["import", "--file", str(good_file)])
            self.assertNotEqual(rc_sym, 0)
            self.assertIn("Symlink rejected", err_sym)
            self.assertFalse((self.tmp_dir / "instances" / "safe-user").exists())
        finally:
            symlink_in_tpl.unlink(missing_ok=True)

        # Symlink at target instance path must also be rejected
        target_sym = self.tmp_dir / "instances" / "safe-user"
        target_sym.symlink_to(self.tmp_dir)
        try:
            rc_tsym, _, err_tsym = self._run_cli(["import", "--file", str(good_file)])
            self.assertNotEqual(rc_tsym, 0)
            self.assertIn("symlink", err_tsym.lower())
        finally:
            target_sym.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
