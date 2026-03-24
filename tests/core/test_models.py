from __future__ import annotations

import unittest

from openenv.core.models import (
    AgentConfig,
    Manifest,
    OpenClawConfig,
    ProjectConfig,
    RuntimeConfig,
    SandboxConfig,
    SkillConfig,
)
from openenv.core.utils import sha256_text


class ManifestModelTests(unittest.TestCase):
    def test_workspace_files_rewrite_skill_home_paths_for_runtime(self) -> None:
        manifest = Manifest(
            schema_version=1,
            project=ProjectConfig(
                name="Memory Bot",
                version="1.0.0",
                description="Tests rewritten skill paths.",
                runtime="openclaw",
            ),
            runtime=RuntimeConfig(
                base_image="python:3.12-slim@sha256:" + "1" * 64,
                python_version="3.12",
            ),
            agent=AgentConfig(
                agents_md="Agents",
                soul_md="Soul",
                user_md="User",
            ),
            skills=[
                SkillConfig(
                    name="memory-linker",
                    description="Links into OpenClaw memory",
                    content=(
                        "---\n"
                        "name: memory-linker\n"
                        "description: Links into OpenClaw memory\n"
                        "---\n\n"
                        "Read `/home/deus/.openclaw/workspace/memory/projects/demo.md` "
                        "and inspect `$HOME/.openclaw/cache.db`.\n"
                    ),
                    assets={
                        "notes.md": (
                            "Workspace: ${HOME}/.openclaw/workspace/memory/projects/\n"
                            "State: ~/.openclaw/openclaw.json\n"
                        )
                    },
                )
            ],
            openclaw=OpenClawConfig(
                agent_id="memory-bot",
                agent_name="Memory Bot",
                workspace="/srv/openclaw/workspace",
                state_dir="/srv/openclaw",
            ),
        )

        files = manifest.workspace_files()
        skill_md = files["/srv/openclaw/workspace/skills/memory-linker/SKILL.md"]
        asset_md = files["/srv/openclaw/workspace/skills/memory-linker/notes.md"]

        self.assertIn("/srv/openclaw/workspace/memory/projects/demo.md", skill_md)
        self.assertIn("/srv/openclaw/cache.db", skill_md)
        self.assertNotIn("/home/deus/.openclaw", skill_md)
        self.assertNotIn("$HOME/.openclaw", skill_md)

        self.assertIn("/srv/openclaw/workspace/memory/projects/", asset_md)
        self.assertIn("/srv/openclaw/openclaw.json", asset_md)
        self.assertNotIn("${HOME}/.openclaw", asset_md)
        self.assertNotIn("~/.openclaw", asset_md)

        snapshot = manifest.source_snapshot()
        self.assertEqual(
            snapshot["skills"][0]["content_sha256"],
            sha256_text(skill_md),
        )
        self.assertEqual(
            snapshot["skills"][0]["assets"]["notes.md"],
            sha256_text(asset_md),
        )

    def test_openclaw_json_includes_gateway_and_normalized_sandbox_fields(self) -> None:
        manifest = Manifest(
            schema_version=1,
            project=ProjectConfig(
                name="Gateway Bot",
                version="1.0.0",
                description="Tests generated OpenClaw config.",
                runtime="openclaw",
            ),
            runtime=RuntimeConfig(
                base_image="python:3.12-slim@sha256:" + "1" * 64,
                python_version="3.12",
            ),
            agent=AgentConfig(
                agents_md="Agents",
                soul_md="Soul",
                user_md="User",
            ),
            skills=[],
            openclaw=OpenClawConfig(
                agent_id="gateway-bot",
                agent_name="Gateway Bot",
                tools_allow=["shell_command"],
            ),
        )

        config = manifest.openclaw.to_openclaw_json("${OPENCLAW_IMAGE}")

        self.assertEqual(config["gateway"]["mode"], "local")
        self.assertEqual(config["gateway"]["bind"], "lan")
        self.assertEqual(config["gateway"]["auth"]["mode"], "token")
        self.assertEqual(config["gateway"]["auth"]["token"], "${OPENCLAW_GATEWAY_TOKEN}")
        self.assertEqual(config["agents"]["defaults"]["sandbox"]["mode"], "all")
        self.assertEqual(config["agents"]["defaults"]["sandbox"]["backend"], "docker")
        self.assertEqual(config["agents"]["defaults"]["sandbox"]["workspaceAccess"], "rw")
        self.assertEqual(
            config["agents"]["defaults"]["sandbox"]["docker"]["image"],
            "${OPENCLAW_IMAGE}",
        )

    def test_openclaw_json_includes_raw_channel_config(self) -> None:
        manifest = Manifest(
            schema_version=1,
            project=ProjectConfig(
                name="Channel Bot",
                version="1.0.0",
                description="Tests generated channel config.",
                runtime="openclaw",
            ),
            runtime=RuntimeConfig(
                base_image="python:3.12-slim@sha256:" + "1" * 64,
                python_version="3.12",
            ),
            agent=AgentConfig(
                agents_md="Agents",
                soul_md="Soul",
                user_md="User",
            ),
            skills=[],
            openclaw=OpenClawConfig(
                agent_id="channel-bot",
                agent_name="Channel Bot",
                channels={
                    "telegram": {
                        "enabled": True,
                        "allowFrom": ["123456"],
                    },
                    "googlechat": {
                        "accounts": {
                            "workspace": {
                                "serviceAccountFile": "/opt/secrets/googlechat.json",
                            }
                        }
                    },
                },
            ),
        )

        config = manifest.openclaw.to_openclaw_json("${OPENCLAW_IMAGE}")

        self.assertEqual(config["channels"]["telegram"]["allowFrom"], ["123456"])
        self.assertTrue(config["channels"]["telegram"]["enabled"])
        self.assertEqual(
            config["channels"]["googlechat"]["accounts"]["workspace"]["serviceAccountFile"],
            "/opt/secrets/googlechat.json",
        )

    def test_openclaw_json_omits_docker_backend_when_sandbox_is_off(self) -> None:
        manifest = Manifest(
            schema_version=1,
            project=ProjectConfig(
                name="Outer Sandbox Bot",
                version="1.0.0",
                description="Runs inside an outer container sandbox.",
                runtime="openclaw",
            ),
            runtime=RuntimeConfig(
                base_image="python:3.12-slim@sha256:" + "1" * 64,
                python_version="3.12",
            ),
            agent=AgentConfig(
                agents_md="Agents",
                soul_md="Soul",
                user_md="User",
            ),
            skills=[],
            openclaw=OpenClawConfig(
                agent_id="outer-sandbox-bot",
                agent_name="Outer Sandbox Bot",
                sandbox=SandboxConfig(mode="off"),
            ),
        )

        config = manifest.openclaw.to_openclaw_json("${OPENCLAW_IMAGE}")

        self.assertEqual(config["agents"]["defaults"]["sandbox"], {"mode": "off"})
