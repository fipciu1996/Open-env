from __future__ import annotations

import tomllib
import shutil
import unittest
from pathlib import Path

from openenv.core.skills import MANDATORY_SKILL_SOURCES
from openenv.core.errors import ValidationError
from openenv.manifests.loader import load_manifest, parse_manifest


TESTS_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = TESTS_ROOT / "fixtures"
TEMP_ROOT = TESTS_ROOT / "_tmp"
TEMP_ROOT.mkdir(exist_ok=True)


class ManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.work_dir = TEMP_ROOT / "manifest"
        if self.work_dir.exists():
            shutil.rmtree(self.work_dir, ignore_errors=True)
        self.work_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.work_dir, ignore_errors=True)

    def test_load_fixture_manifest(self) -> None:
        manifest, _ = load_manifest(FIXTURES / "example.openenv.toml")

        self.assertEqual(manifest.project.name, "ops-agent")
        self.assertEqual(manifest.runtime.user, "agent")
        self.assertEqual(manifest.openclaw.agent_name, "Operations Agent")
        self.assertEqual(manifest.runtime.node_packages, ["typescript@5.8.3"])
        self.assertEqual(len(manifest.skills), 6)
        self.assertEqual(
            [skill.source for skill in manifest.skills[: len(MANDATORY_SKILL_SOURCES)]],
            list(MANDATORY_SKILL_SOURCES),
        )

    def test_rejects_inline_sensitive_env(self) -> None:
        raw = """
schema_version = 1

[project]
name = "bad-agent"
version = "0.1.0"
description = "bad"
runtime = "openclaw"

[runtime]
base_image = "python:3.12-slim@sha256:1111111111111111111111111111111111111111111111111111111111111111"
python_version = "3.12"
python_packages = ["requests==2.32.3"]
env = { OPENAI_API_KEY = "super-secret-value" }

[agent]
agents_md = "a"
soul_md = "b"
user_md = "c"

[openclaw]
agent_id = "main"
agent_name = "Bad Agent"

[openclaw.sandbox]
mode = "workspace-write"
scope = "session"
workspace_access = "full"
network = "none"
read_only_root = false
"""
        with self.assertRaises(ValidationError):
            parse_manifest(tomllib.loads(raw))

    def test_parse_manifest_adds_mandatory_skills_when_missing(self) -> None:
        raw = """
schema_version = 1

[project]
name = "base-agent"
version = "0.1.0"
description = "minimal"
runtime = "openclaw"

[runtime]
base_image = "python:3.12-slim@sha256:1111111111111111111111111111111111111111111111111111111111111111"
python_version = "3.12"

[agent]
agents_md = "a"
soul_md = "b"
user_md = "c"

[openclaw]
agent_id = "main"
agent_name = "Base Agent"

[openclaw.sandbox]
mode = "workspace-write"
scope = "session"
workspace_access = "full"
network = "none"
read_only_root = false
"""
        manifest = parse_manifest(tomllib.loads(raw))

        self.assertEqual(
            [skill.source for skill in manifest.skills],
            list(MANDATORY_SKILL_SOURCES),
        )

    def test_load_manifest_reads_secret_refs_from_sidecar_env(self) -> None:
        manifest_path = self.work_dir / "openenv.toml"
        manifest_path.write_text(
            """
schema_version = 1

[project]
name = "env-agent"
version = "0.1.0"
description = "env-backed"
runtime = "openclaw"

[runtime]
base_image = "python:3.12-slim@sha256:1111111111111111111111111111111111111111111111111111111111111111"
python_version = "3.12"
python_packages = ["requests==2.32.3"]

[agent]
agents_md = "a"
soul_md = "b"
user_md = "c"

[openclaw]
agent_id = "main"
agent_name = "Env Agent"

[openclaw.sandbox]
mode = "workspace-write"
scope = "session"
workspace_access = "full"
network = "none"
read_only_root = false
""".strip(),
            encoding="utf-8",
        )
        (self.work_dir / ".env").write_text(
            "# Secret references\nOPENAI_API_KEY=\nDB_PASSWORD=secret\n",
            encoding="utf-8",
        )

        manifest, _ = load_manifest(manifest_path)

        self.assertEqual(
            [secret.name for secret in manifest.runtime.secret_refs],
            ["OPENAI_API_KEY", "DB_PASSWORD"],
        )

    def test_load_manifest_reads_agent_docs_from_local_markdown_refs(self) -> None:
        manifest_path = self.work_dir / "openenv.toml"
        manifest_path.write_text(
            """
schema_version = 1

[project]
name = "ref-agent"
version = "0.1.0"
description = "file-backed docs"
runtime = "openclaw"

[runtime]
base_image = "python:3.12-slim@sha256:1111111111111111111111111111111111111111111111111111111111111111"
python_version = "3.12"

[agent]
agents_md = "AGENTS.md"
soul_md = "SOUL.md"
user_md = "USER.md"
identity_md = "IDENTITY.md"
tools_md = "TOOLS.md"
memory_seed = "memory.md"

[openclaw]
agent_id = "main"
agent_name = "Ref Agent"

[openclaw.sandbox]
mode = "workspace-write"
scope = "session"
workspace_access = "full"
network = "none"
read_only_root = false
""".strip(),
            encoding="utf-8",
        )
        (self.work_dir / "AGENTS.md").write_text("# Agent Contract\n", encoding="utf-8")
        (self.work_dir / "SOUL.md").write_text("# Soul\n", encoding="utf-8")
        (self.work_dir / "USER.md").write_text("# User\n", encoding="utf-8")
        (self.work_dir / "IDENTITY.md").write_text("# Identity\n", encoding="utf-8")
        (self.work_dir / "TOOLS.md").write_text("# Tools\n", encoding="utf-8")
        (self.work_dir / "memory.md").write_text(
            "Remember the operating model.\nKeep summaries short.\n",
            encoding="utf-8",
        )

        manifest, _ = load_manifest(manifest_path)

        self.assertEqual(manifest.agent.agents_md, "# Agent Contract\n")
        self.assertEqual(manifest.agent.agents_md_ref, "AGENTS.md")
        self.assertEqual(manifest.agent.soul_md_ref, "SOUL.md")
        self.assertEqual(manifest.agent.user_md_ref, "USER.md")
        self.assertEqual(manifest.agent.identity_md_ref, "IDENTITY.md")
        self.assertEqual(manifest.agent.tools_md_ref, "TOOLS.md")
        self.assertEqual(manifest.agent.memory_seed_ref, "memory.md")
        self.assertEqual(
            manifest.agent.memory_seed,
            ["Remember the operating model.", "Keep summaries short."],
        )

    def test_rejects_manifest_with_both_toml_and_sidecar_secret_refs(self) -> None:
        manifest_path = self.work_dir / "openenv.toml"
        manifest_path.write_text(
            """
schema_version = 1

[project]
name = "env-agent"
version = "0.1.0"
description = "env-backed"
runtime = "openclaw"

[runtime]
base_image = "python:3.12-slim@sha256:1111111111111111111111111111111111111111111111111111111111111111"
python_version = "3.12"

[[runtime.secret_refs]]
name = "OPENAI_API_KEY"
source = "env:OPENAI_API_KEY"
required = true

[agent]
agents_md = "a"
soul_md = "b"
user_md = "c"

[openclaw]
agent_id = "main"
agent_name = "Env Agent"

[openclaw.sandbox]
mode = "workspace-write"
scope = "session"
workspace_access = "full"
network = "none"
read_only_root = false
""".strip(),
            encoding="utf-8",
        )
        (self.work_dir / ".env").write_text("OPENAI_API_KEY=\n", encoding="utf-8")

        with self.assertRaises(ValidationError):
            load_manifest(manifest_path)

    def test_rejects_skill_asset_traversal(self) -> None:
        raw = """
schema_version = 1

[project]
name = "bad-agent"
version = "0.1.0"
description = "bad"
runtime = "openclaw"

[runtime]
base_image = "python:3.12-slim@sha256:1111111111111111111111111111111111111111111111111111111111111111"
python_version = "3.12"
python_packages = ["requests==2.32.3"]

[agent]
agents_md = "a"
soul_md = "b"
user_md = "c"

[[skills]]
name = "bad"
description = "bad"
content = "---\\nname: bad\\ndescription: bad\\n---\\n"
assets = { "../escape.txt" = "nope" }

[openclaw]
agent_id = "main"
agent_name = "Bad Agent"

[openclaw.sandbox]
mode = "workspace-write"
scope = "session"
workspace_access = "full"
network = "none"
read_only_root = false
"""
        with self.assertRaises(ValidationError):
            parse_manifest(tomllib.loads(raw))

    def test_rejects_agent_doc_reference_outside_manifest_directory(self) -> None:
        raw = """
schema_version = 1

[project]
name = "bad-agent"
version = "0.1.0"
description = "bad"
runtime = "openclaw"

[runtime]
base_image = "python:3.12-slim@sha256:1111111111111111111111111111111111111111111111111111111111111111"
python_version = "3.12"

[agent]
agents_md = "../AGENTS.md"
soul_md = "b"
user_md = "c"

[openclaw]
agent_id = "main"
agent_name = "Bad Agent"

[openclaw.sandbox]
mode = "workspace-write"
scope = "session"
workspace_access = "full"
network = "none"
read_only_root = false
"""
        with self.assertRaises(ValidationError):
            parse_manifest(tomllib.loads(raw), base_dir=self.work_dir)
