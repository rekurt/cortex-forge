import os
import pathlib
import subprocess
import tempfile
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
PROVISION_SCRIPT = REPO_ROOT / "scripts" / "provision-hermes-data.sh"


class TestSymlinkProtection(unittest.TestCase):
    """Ensure host provisioning scripts refuse to follow symlinks inside user-writable directories."""

    def test_provision_rejects_soul_md_symlink_to_secret(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "scripts").mkdir()
            (root / "instances" / "_template").mkdir(parents=True)
            (root / "instances" / "_template" / "hermes_config.yaml.template").write_text("model:\n  provider: anthropic\n")

            # Copy provision script into temp root
            script_copy = root / "scripts" / "provision-hermes-data.sh"
            script_copy.write_text(PROVISION_SCRIPT.read_text())
            script_copy.chmod(0o755)

            secret_env = root / ".env"
            secret_env.write_text("ANTHROPIC_API_KEY=test-root-key\nQUOTA_KEY_USER1=quota-user1-abc\n")

            user_dir = root / "instances" / "user1"
            (user_dir / "workspace").mkdir(parents=True)
            (user_dir / "hermes_data").mkdir(parents=True)
            (user_dir / ".env").write_text("TELEGRAM_BOT_TOKEN=123:abc\nTELEGRAM_ALLOWED_USERS=111\n")

            # Attacker replaces workspace/SOUL.md with a symlink to root .env
            soul_link = user_dir / "workspace" / "SOUL.md"
            os.symlink(secret_env, soul_link)

            res = subprocess.run(
                ["bash", str(script_copy), "user1"],
                cwd=str(root),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(res.returncode, 0, msg=res.stderr)
            target_soul = user_dir / "hermes_data" / "SOUL.md"
            self.assertFalse(
                target_soul.exists(),
                "hermes_data/SOUL.md must NOT be created when workspace/SOUL.md is a symlink",
            )

    def test_provision_copies_regular_soul_md(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "scripts").mkdir()
            (root / "instances" / "_template").mkdir(parents=True)
            (root / "instances" / "_template" / "hermes_config.yaml.template").write_text("model:\n  provider: anthropic\n")

            script_copy = root / "scripts" / "provision-hermes-data.sh"
            script_copy.write_text(PROVISION_SCRIPT.read_text())
            script_copy.chmod(0o755)

            (root / ".env").write_text("ANTHROPIC_API_KEY=test-root-key\nQUOTA_KEY_USER1=quota-user1-xyz\n")

            user_dir = root / "instances" / "user1"
            (user_dir / "workspace").mkdir(parents=True)
            (user_dir / "hermes_data").mkdir(parents=True)
            (user_dir / ".env").write_text("TELEGRAM_BOT_TOKEN=123:abc\nTELEGRAM_ALLOWED_USERS=111\n")
            (user_dir / "workspace" / "SOUL.md").write_text("# Regular Soul Persona\n")

            res = subprocess.run(
                ["bash", str(script_copy), "user1"],
                cwd=str(root),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(res.returncode, 0, msg=res.stderr)
            target_soul = user_dir / "hermes_data" / "SOUL.md"
            self.assertTrue(target_soul.exists())
            self.assertEqual(target_soul.read_text(), "# Regular Soul Persona\n")
            # Verify strict quota key separation
            env_text = (user_dir / "hermes_data" / ".env").read_text()
            self.assertIn("ANTHROPIC_API_KEY=quota-user1-xyz", env_text)
            self.assertNotIn("test-root-key", env_text)


if __name__ == "__main__":
    unittest.main()
