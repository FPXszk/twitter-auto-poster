"""Validate repo-local skill assets under .agents/skills/."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase, main

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO_ROOT / ".agents" / "skills"


class SkillDirectoryTest(TestCase):
    """Ensure all expected skills exist and have a valid SKILL.md."""

    EXPECTED_SKILLS = [
        "twitter-cli",
        "research-playbook",
        "github-actions-failure-debugging",
        "japanese-post-humanizer",
        "repo-planning-discipline",
    ]

    def test_all_expected_skill_directories_exist(self) -> None:
        for skill_name in self.EXPECTED_SKILLS:
            skill_dir = SKILLS_DIR / skill_name
            self.assertTrue(
                skill_dir.is_dir(),
                f"Expected skill directory does not exist: {skill_dir}",
            )

    def test_all_skills_have_skill_md(self) -> None:
        for skill_name in self.EXPECTED_SKILLS:
            skill_md = SKILLS_DIR / skill_name / "SKILL.md"
            self.assertTrue(
                skill_md.is_file(),
                f"Missing SKILL.md for skill: {skill_name}",
            )

    def test_skill_md_is_non_empty(self) -> None:
        for skill_name in self.EXPECTED_SKILLS:
            skill_md = SKILLS_DIR / skill_name / "SKILL.md"
            if not skill_md.is_file():
                continue
            content = skill_md.read_text(encoding="utf-8").strip()
            self.assertTrue(
                len(content) > 50,
                f"SKILL.md for {skill_name} is too short ({len(content)} chars)",
            )

    def test_skill_md_has_frontmatter(self) -> None:
        for skill_name in self.EXPECTED_SKILLS:
            skill_md = SKILLS_DIR / skill_name / "SKILL.md"
            if not skill_md.is_file():
                continue
            content = skill_md.read_text(encoding="utf-8")
            self.assertTrue(
                content.startswith("---"),
                f"SKILL.md for {skill_name} must start with YAML frontmatter (---)",
            )


class JapanesePostHumanizerSkillTest(TestCase):
    """Validate japanese-post-humanizer skill content."""

    _SKILL_PATH = SKILLS_DIR / "japanese-post-humanizer" / "SKILL.md"

    def test_skill_mentions_anti_ai_guidance(self) -> None:
        if not self._SKILL_PATH.is_file():
            self.skipTest("Skill file not yet created")
        content = self._SKILL_PATH.read_text(encoding="utf-8")
        self.assertTrue(
            "AI" in content or "機械的" in content,
            "Skill must contain anti-AI writing guidance",
        )

    def test_skill_is_scoped_to_japanese(self) -> None:
        if not self._SKILL_PATH.is_file():
            self.skipTest("Skill file not yet created")
        content = self._SKILL_PATH.read_text(encoding="utf-8")
        self.assertTrue(
            "Japanese" in content or "日本語" in content,
            "Skill must be scoped to Japanese content",
        )


class RepoPlanningDisciplineSkillTest(TestCase):
    """Validate repo-planning-discipline skill content."""

    _SKILL_PATH = SKILLS_DIR / "repo-planning-discipline" / "SKILL.md"

    def test_skill_references_exec_plans(self) -> None:
        if not self._SKILL_PATH.is_file():
            self.skipTest("Skill file not yet created")
        content = self._SKILL_PATH.read_text(encoding="utf-8")
        self.assertIn("exec-plans", content)

    def test_skill_references_sql_todos(self) -> None:
        if not self._SKILL_PATH.is_file():
            self.skipTest("Skill file not yet created")
        content = self._SKILL_PATH.read_text(encoding="utf-8")
        self.assertTrue(
            "SQL" in content or "sql" in content or "todos" in content,
            "Skill must reference SQL todos workflow",
        )

    def test_skill_references_session_plan(self) -> None:
        if not self._SKILL_PATH.is_file():
            self.skipTest("Skill file not yet created")
        content = self._SKILL_PATH.read_text(encoding="utf-8")
        self.assertTrue(
            "plan.md" in content or "session" in content.lower(),
            "Skill must reference session plan.md",
        )

    def test_skill_does_not_introduce_upstream_root_files(self) -> None:
        if not self._SKILL_PATH.is_file():
            self.skipTest("Skill file not yet created")
        content = self._SKILL_PATH.read_text(encoding="utf-8")
        for upstream_file in ["task_plan.md", "findings.md", "progress.md"]:
            self.assertNotIn(
                upstream_file,
                content,
                f"Skill must not introduce upstream root-level file: {upstream_file}",
            )


if __name__ == "__main__":
    main()
