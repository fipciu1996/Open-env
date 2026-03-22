from __future__ import annotations

import unittest

from openenv.core.skills import (
    FREERIDE_SKILL_NAME,
    MANDATORY_SKILL_SOURCES,
    build_catalog_skill,
    ensure_mandatory_skills,
    merge_mandatory_skill_sources,
    skill_name_for_source,
)


class SkillsTests(unittest.TestCase):
    def test_merge_mandatory_skill_sources_keeps_defaults_first(self) -> None:
        merged = merge_mandatory_skill_sources(
            ["kralsamwise/kdp-publisher", "self-improving-agent"]
        )

        self.assertEqual(
            merged,
            [
                "deus-context-engine",
                "self-improving-agent",
                "skill-security-review",
                "freeride",
                "agent-browser-clawdbot",
                "kralsamwise/kdp-publisher",
            ],
        )

    def test_ensure_mandatory_skills_adds_missing_references(self) -> None:
        skills = ensure_mandatory_skills(
            [build_catalog_skill("kralsamwise/kdp-publisher")]
        )

        self.assertEqual(
            [skill.source for skill in skills if skill.source in MANDATORY_SKILL_SOURCES],
            list(MANDATORY_SKILL_SOURCES),
        )

    def test_ensure_mandatory_skills_does_not_duplicate_existing_skill(self) -> None:
        skills = ensure_mandatory_skills(
            [
                build_catalog_skill("deus-context-engine", mandatory=True),
                build_catalog_skill("kralsamwise/kdp-publisher"),
            ]
        )

        self.assertEqual(
            [skill.source for skill in skills].count("deus-context-engine"),
            1,
        )

    def test_skill_name_for_source_uses_catalog_overrides(self) -> None:
        self.assertEqual(skill_name_for_source("freeride"), FREERIDE_SKILL_NAME)
