#!/usr/bin/env python3
"""
Tests for qmd skill (service-agent/skills/qmd/run.py).

Uses unittest with temporary directories containing .md files to test search.
Overrides QMD_*_DIR env vars to point at test fixtures.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

# Path to run.py
RUN_PY = os.path.join(
    os.path.dirname(__file__), "..", "service-agent", "skills", "qmd", "run.py"
)


class TestQmd(unittest.TestCase):

    tmpdir = None

    @classmethod
    def setUpClass(cls):
        """Create temporary directory structure with .md files for testing."""
        cls.tmpdir = tempfile.mkdtemp(prefix="qmd_test_")

        # Create workspace structure
        ws = os.path.join(cls.tmpdir, "workspace")
        os.makedirs(ws)
        with open(os.path.join(ws, "SOUL.md"), "w") as f:
            f.write("# Soul\n\nI am a corporate assistant.\nquota-proxy controls tokens.\n")
        with open(os.path.join(ws, "NOTES.md"), "w") as f:
            f.write("# Notes\n\nNote about broker and messages.\nBROKER_KEY is important for auth.\n")

        # Create shared/docs structure
        cls.docs_dir = os.path.join(cls.tmpdir, "shared", "docs")
        os.makedirs(cls.docs_dir)
        with open(os.path.join(cls.docs_dir, "architecture.md"), "w") as f:
            f.write("# Architecture\n\nquota-proxy controls usage.\nrate-limit protects the API.\n")

        # Create shared/skills structure
        cls.skills_dir = os.path.join(cls.tmpdir, "shared", "skills", "test-skill")
        os.makedirs(cls.skills_dir)
        with open(os.path.join(cls.skills_dir, "SKILL.md"), "w") as f:
            f.write("# Test Skill\n\nThis skill does nothing special.\nNo quota references here.\n")

        # Create a non-md file (should be ignored)
        with open(os.path.join(ws, "data.txt"), "w") as f:
            f.write("quota-proxy mentioned in txt file\n")

        # Set env paths
        cls.workspace_dir = ws
        cls.shared_docs_dir = cls.docs_dir
        cls.shared_skills_dir = os.path.join(cls.tmpdir, "shared", "skills")

    @classmethod
    def tearDownClass(cls):
        if cls.tmpdir:
            shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def _run_skill(self, params):
        """Run qmd skill with QMD_*_DIR env vars pointing to test fixtures."""
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": os.environ.get("HOME", ""),
            "QMD_WORKSPACE_DIR": self.workspace_dir,
            "QMD_SHARED_DOCS_DIR": self.shared_docs_dir,
            "QMD_SHARED_SKILLS_DIR": self.shared_skills_dir,
        }
        proc = subprocess.run(
            [sys.executable, RUN_PY],
            input=json.dumps(params),
            capture_output=True,
            text=True,
            timeout=15,
            env=env,
        )
        if proc.returncode != 0 and not proc.stdout.strip():
            self.fail(f"run.py crashed: stderr={proc.stderr}")
        return json.loads(proc.stdout)

    # ── Basic search ─────────────────────────────────────────────────────

    def test_search_quota_all_scope(self):
        result = self._run_skill({"query": "quota"})
        self.assertEqual(result["status"], "ok")
        self.assertGreaterEqual(result["total_files_with_matches"], 2)
        files = [r["file"] for r in result["results"]]
        found_ws = any("workspace" in f and "SOUL" in f for f in files)
        found_docs = any("architecture" in f for f in files)
        self.assertTrue(found_ws, f"Expected workspace/SOUL.md in results, got: {files}")
        self.assertTrue(found_docs, f"Expected architecture.md in results, got: {files}")

    def test_search_workspace_scope(self):
        result = self._run_skill({"query": "BROKER_KEY", "scope": "workspace"})
        self.assertEqual(result["status"], "ok")
        self.assertGreaterEqual(result["total_files_with_matches"], 1)
        for r in result["results"]:
            self.assertIn("workspace", r["file"])

    def test_search_shared_scope(self):
        result = self._run_skill({"query": "rate-limit", "scope": "shared"})
        self.assertEqual(result["status"], "ok")
        self.assertGreaterEqual(result["total_files_with_matches"], 1)
        for r in result["results"]:
            self.assertIn("shared", r["file"])

    def test_search_skills_scope(self):
        result = self._run_skill({"query": "nothing special", "scope": "skills"})
        self.assertEqual(result["status"], "ok")
        self.assertGreaterEqual(result["total_files_with_matches"], 1)
        for r in result["results"]:
            self.assertIn("skills", r["file"])

    # ── Regex search ─────────────────────────────────────────────────────

    def test_regex_search(self):
        result = self._run_skill({"query": "quota[_-]proxy|rate.limit"})
        self.assertEqual(result["status"], "ok")
        self.assertGreaterEqual(result["total_files_with_matches"], 2)

    # ── No results ───────────────────────────────────────────────────────

    def test_no_results(self):
        result = self._run_skill({"query": "xyznonexistent123"})
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["total_files_with_matches"], 0)
        self.assertEqual(result["total_matches"], 0)

    # ── Context lines ────────────────────────────────────────────────────

    def test_context_included(self):
        result = self._run_skill({"query": "quota-proxy", "scope": "workspace"})
        self.assertEqual(result["status"], "ok")
        self.assertGreater(len(result["results"]), 0)
        first = result["results"][0]
        self.assertGreater(len(first["matches"]), 0)
        self.assertIn("context", first["matches"][0])
        self.assertIn("line_number", first["matches"][0])

    # ── max_results ──────────────────────────────────────────────────────

    def test_max_results(self):
        result = self._run_skill({"query": ".", "max_results": 2})
        self.assertEqual(result["status"], "ok")
        self.assertLessEqual(result["total_files_with_matches"], 2)

    # ── Error handling ───────────────────────────────────────────────────

    def test_missing_query(self):
        result = self._run_skill({})
        self.assertEqual(result["status"], "error")
        self.assertIn("query", result["error"].lower())

    def test_unknown_scope(self):
        result = self._run_skill({"query": "test", "scope": "invalid"})
        self.assertEqual(result["status"], "error")
        self.assertIn("scope", result["error"].lower())

    # ── Non-md files ignored ─────────────────────────────────────────────

    def test_txt_files_ignored(self):
        result = self._run_skill({"query": "mentioned in txt", "scope": "workspace"})
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["total_files_with_matches"], 0)

    # ── Case insensitive ─────────────────────────────────────────────────

    def test_case_insensitive(self):
        result = self._run_skill({"query": "QUOTA"})
        self.assertEqual(result["status"], "ok")
        self.assertGreater(result["total_files_with_matches"], 0)

    # ── Metadata fields ──────────────────────────────────────────────────

    def test_files_scanned_reported(self):
        result = self._run_skill({"query": "anything"})
        self.assertEqual(result["status"], "ok")
        self.assertIn("files_scanned", result)
        self.assertGreater(result["files_scanned"], 0)

    def test_elapsed_ms_reported(self):
        result = self._run_skill({"query": "anything"})
        self.assertEqual(result["status"], "ok")
        self.assertIn("elapsed_ms", result)
        self.assertIsInstance(result["elapsed_ms"], int)

    # ── Invalid regex falls back to literal ──────────────────────────────

    def test_invalid_regex_falls_back(self):
        result = self._run_skill({"query": "[invalid regex"})
        self.assertEqual(result["status"], "ok")
        # Should not crash, falls back to literal search


if __name__ == "__main__":
    unittest.main()
