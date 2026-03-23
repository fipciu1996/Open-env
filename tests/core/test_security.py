from __future__ import annotations

import unittest

from openenv.core.models import (
    AgentConfig,
    Manifest,
    OpenClawConfig,
    ProjectConfig,
    RuntimeConfig,
    SandboxConfig,
)
from openenv.core.security import assess_manifest_security, assess_runtime_env_security


class SecurityAssessmentTests(unittest.TestCase):
    def test_assess_manifest_security_reports_risky_explicit_choices(self) -> None:
        manifest = Manifest(
            schema_version=1,
            project=ProjectConfig(
                name="Risk Bot",
                version="1.0.0",
                description="Risky but explicit operator choices.",
                runtime="openclaw",
            ),
            runtime=RuntimeConfig(
                base_image="python:3.12-slim",
                python_version="3.12",
                user="root",
            ),
            agent=AgentConfig(
                agents_md="Agents",
                soul_md="Soul",
                user_md="User",
            ),
            skills=[],
            openclaw=OpenClawConfig(
                agent_id="risk-bot",
                agent_name="Risk Bot",
                tools_allow=["*", "shell_command"],
                sandbox=SandboxConfig(
                    mode="workspace-write",
                    scope="session",
                    workspace_access="full",
                    network="host",
                    read_only_root=False,
                ),
            ),
        )

        advisories = assess_manifest_security(manifest)

        self.assertTrue(
            any("not pinned with a digest" in advisory for advisory in advisories)
        )
        self.assertTrue(any("set to root" in advisory for advisory in advisories))
        self.assertTrue(any("read_only_root is disabled" in advisory for advisory in advisories))
        self.assertTrue(any("sandbox.network='host'" in advisory for advisory in advisories))
        self.assertTrue(any("wildcard entries" in advisory for advisory in advisories))
        self.assertTrue(any("includes shell_command" in advisory for advisory in advisories))

    def test_assess_manifest_security_allows_bridge_network_without_network_warning(self) -> None:
        manifest = Manifest(
            schema_version=1,
            project=ProjectConfig(
                name="Bridge Bot",
                version="1.0.0",
                description="Bridge network with host isolation preserved.",
                runtime="openclaw",
            ),
            runtime=RuntimeConfig(
                base_image="python:3.12-slim@sha256:" + "1" * 64,
                python_version="3.12",
                user="agent",
            ),
            agent=AgentConfig(
                agents_md="Agents",
                soul_md="Soul",
                user_md="User",
            ),
            skills=[],
            openclaw=OpenClawConfig(
                agent_id="bridge-bot",
                agent_name="Bridge Bot",
                tools_allow=[],
                sandbox=SandboxConfig(
                    mode="workspace-write",
                    scope="session",
                    workspace_access="full",
                    network="bridge",
                    read_only_root=True,
                ),
            ),
        )

        advisories = assess_manifest_security(manifest)

        self.assertFalse(any("sandbox.network" in advisory for advisory in advisories))

    def test_assess_runtime_env_security_reports_public_bind_and_insecure_ws(self) -> None:
        advisories = assess_runtime_env_security(
            {
                "OPENCLAW_GATEWAY_HOST_BIND": "0.0.0.0",
                "OPENCLAW_BRIDGE_HOST_BIND": "192.168.1.10",
                "OPENCLAW_ALLOW_INSECURE_PRIVATE_WS": "1",
            }
        )

        self.assertTrue(any("gateway beyond localhost" in advisory for advisory in advisories))
        self.assertTrue(any("bridge beyond localhost" in advisory for advisory in advisories))
        self.assertTrue(any("weaken" in advisory for advisory in advisories))
