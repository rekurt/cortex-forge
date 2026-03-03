#!/usr/bin/env python3
"""
Tests for SOUL.md and IDENTITY.md template content.

Validates that the template files contain required personality sections
(workaround thinking, empathy) and that admin SOUL.md is not affected.
Uses stdlib only.
"""

import os
import unittest


REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")


def _read_file(relative_path):
    path = os.path.join(REPO_ROOT, relative_path)
    with open(path) as f:
        return f.read()


class TestTemplateSoulMd(unittest.TestCase):
    """Validate template SOUL.md has required personality sections."""

    def setUp(self):
        self.soul = _read_file(
            "instances/_template/workspace/SOUL.md"
        )

    def test_has_workaround_section(self):
        """SOUL.md must have a workaround-thinking section."""
        self.assertIn("Workaround", self.soul,
                       "SOUL.md must contain workaround section")

    def test_has_workaround_examples(self):
        """Workaround section must include concrete examples."""
        self.assertIn("обходной путь", self.soul.lower(),
                       "SOUL.md must mention 'обходной путь'")

    def test_has_empathy_section(self):
        """SOUL.md must have a section about empathy/caring."""
        self.assertIn("Участливость", self.soul,
                       "SOUL.md must contain участливость section")

    def test_has_alternative_after_no(self):
        """SOUL.md must instruct to always offer alternatives after 'no'."""
        soul_lower = self.soul.lower()
        has_alternative_instruction = (
            "альтернатив" in soul_lower
            or "но можно" in soul_lower
            or "но есть" in soul_lower
        )
        self.assertTrue(has_alternative_instruction,
                        "SOUL.md must instruct to offer alternatives")

    def test_keeps_directness(self):
        """SOUL.md must retain the directness rule."""
        self.assertIn("Прямо", self.soul,
                       "SOUL.md must keep directness rule")

    def test_keeps_curiosity(self):
        """SOUL.md must retain the curiosity section."""
        self.assertIn("Любопытство", self.soul,
                       "SOUL.md must keep curiosity section")

    def test_keeps_monkey_theme(self):
        """SOUL.md must retain the capuchin monkey theme."""
        self.assertIn("капуцин", self.soul.lower(),
                       "SOUL.md must reference капуцин")

    def test_no_sycophancy_phrases(self):
        """SOUL.md must still ban sycophantic phrases."""
        self.assertIn("НИКОГДА не писать", self.soul,
                       "SOUL.md must keep the ban on sycophantic phrases")

    def test_warm_tone_not_cold(self):
        """SOUL.md should not have a bare 'Нет.' without alternative."""
        # The old pattern was: «Нет. [почему] Но могу вот это:»
        # The new pattern should offer a workaround path
        soul_lower = self.soul.lower()
        has_warmth = (
            "загвоздка" in soul_lower
            or "обходной" in soul_lower
            or "есть путь" in soul_lower
        )
        self.assertTrue(has_warmth,
                        "SOUL.md should use warm phrasing for obstacles")


class TestTemplateIdentityMd(unittest.TestCase):
    """Validate template IDENTITY.md has updated vibe."""

    def setUp(self):
        self.identity = _read_file(
            "instances/_template/workspace/IDENTITY.md"
        )

    def test_vibe_has_empathy(self):
        """Vibe must include empathy/caring keyword."""
        self.assertIn("участливый", self.identity.lower(),
                       "IDENTITY.md vibe must include 'участливый'")

    def test_vibe_has_resourcefulness(self):
        """Vibe must include resourcefulness keyword."""
        self.assertIn("находчивый", self.identity.lower(),
                       "IDENTITY.md vibe must include 'находчивый'")

    def test_vibe_has_playfulness(self):
        """Vibe must include playfulness keyword."""
        self.assertIn("озорной", self.identity.lower(),
                       "IDENTITY.md vibe must include 'озорной'")

    def test_keeps_monkey_emoji(self):
        """IDENTITY.md must keep the monkey emoji."""
        self.assertIn("🐒", self.identity)


class TestAdminSoulNotModified(unittest.TestCase):
    """Ensure admin SOUL.md is separate from template."""

    ADMIN_WORKSPACE = os.path.join(REPO_ROOT, "..", "admin-workspace")

    def test_admin_soul_exists(self):
        """Admin SOUL.md must exist (skipped if workspace not deployed)."""
        path = os.path.join(self.ADMIN_WORKSPACE, "SOUL.md")
        if not os.path.exists(self.ADMIN_WORKSPACE):
            self.skipTest("admin-workspace not deployed (lives outside repo)")
        self.assertTrue(os.path.exists(path),
                        "Admin SOUL.md must exist in ../admin-workspace/")

    def test_admin_soul_differs_from_template(self):
        """Admin SOUL.md must NOT have the template's workaround section."""
        path = os.path.join(self.ADMIN_WORKSPACE, "SOUL.md")
        if not os.path.exists(path):
            self.skipTest("admin-workspace not deployed (lives outside repo)")
        with open(path) as f:
            admin_soul = f.read()
        self.assertNotIn("Workaround", admin_soul,
                          "Admin SOUL.md must NOT contain the template's Workaround section")


if __name__ == "__main__":
    unittest.main()
