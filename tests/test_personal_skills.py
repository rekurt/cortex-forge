#!/usr/bin/env python3
"""
Tests for personal skills infrastructure (Task 7).

Verifies:
- Template workspace has skills/ directory with .gitkeep
- add-user.sh creates skills/ directory for new instances
- TOOLS.md documents personal skills
- shared/docs/common/SKILLS.md documents Personal vs Shared
"""

import os
import re
import subprocess
import sys
import tempfile
import unittest

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")


class TestPersonalSkillsTemplate(unittest.TestCase):
    """Verify template workspace has skills/ directory."""

    def test_template_skills_dir_exists(self):
        skills_dir = os.path.join(
            PROJECT_ROOT, "instances", "_template", "workspace", "skills"
        )
        self.assertTrue(
            os.path.isdir(skills_dir),
            f"Template skills directory missing: {skills_dir}",
        )

    def test_template_skills_gitkeep_exists(self):
        gitkeep = os.path.join(
            PROJECT_ROOT,
            "instances",
            "_template",
            "workspace",
            "skills",
            ".gitkeep",
        )
        self.assertTrue(
            os.path.isfile(gitkeep),
            f".gitkeep missing in template skills: {gitkeep}",
        )


class TestAddUserSkillsDir(unittest.TestCase):
    """Verify add-user.sh creates skills/ directory."""

    def test_add_user_script_has_skills_mkdir(self):
        script_path = os.path.join(PROJECT_ROOT, "scripts", "add-user.sh")
        with open(script_path) as f:
            content = f.read()
        # Verify it's a mkdir command that creates skills directory
        self.assertTrue(
            re.search(r'mkdir\s+-p.*skills', content),
            "add-user.sh should have mkdir -p for skills directory",
        )


class TestToolsDocumentation(unittest.TestCase):
    """Verify TOOLS.md template documents personal skills."""

    def setUp(self):
        tools_path = os.path.join(
            PROJECT_ROOT, "instances", "_template", "workspace", "TOOLS.md"
        )
        with open(tools_path) as f:
            self.content = f.read()

    def test_has_personal_skills_section(self):
        self.assertIn(
            "Личные скиллы",
            self.content,
            "TOOLS.md should have 'Личные скиллы' section",
        )

    def test_has_workspace_skills_path(self):
        self.assertIn(
            "workspace/skills/",
            self.content,
            "TOOLS.md should mention workspace/skills/ path",
        )

    def test_has_priority_explanation(self):
        self.assertIn(
            "приоритет",
            self.content.lower(),
            "TOOLS.md should explain priority loading",
        )

    def test_has_skill_creation_instructions(self):
        self.assertIn(
            "SKILL.md",
            self.content,
            "TOOLS.md should mention SKILL.md for creating skills",
        )


class TestSharedSkillsDocumentation(unittest.TestCase):
    """Verify shared/docs/common/SKILLS.md documents Personal vs Shared."""

    def setUp(self):
        skills_path = os.path.join(
            PROJECT_ROOT, "shared", "docs", "common", "SKILLS.md"
        )
        with open(skills_path) as f:
            self.content = f.read()

    def test_has_personal_vs_shared_section(self):
        self.assertIn(
            "Personal vs Shared",
            self.content,
            "SKILLS.md should have 'Personal vs Shared' section",
        )

    def test_has_shared_skills_description(self):
        self.assertIn(
            "Shared Skills",
            self.content,
            "SKILLS.md should describe shared skills",
        )

    def test_has_personal_skills_description(self):
        self.assertIn(
            "Personal Skills",
            self.content,
            "SKILLS.md should describe personal skills",
        )

    def test_has_priority_explanation(self):
        self.assertIn(
            "приоритет",
            self.content.lower(),
            "SKILLS.md should explain priority loading",
        )

    def test_has_comparison_table(self):
        self.assertIn(
            "Критерий",
            self.content,
            "SKILLS.md should have comparison table",
        )

    def test_has_workspace_skills_path(self):
        self.assertIn(
            "workspace/skills/",
            self.content,
            "SKILLS.md should mention workspace/skills/ path",
        )

    def test_has_shared_skills_path(self):
        self.assertIn(
            "/shared/skills/",
            self.content,
            "SKILLS.md should mention /shared/skills/ path",
        )


if __name__ == "__main__":
    unittest.main()
