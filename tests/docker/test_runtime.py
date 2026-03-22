from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

from openenv.core.errors import CommandError
from openenv.docker.runtime import (
    fetch_container_logs,
    list_running_container_names,
    snapshot_installed_skills,
)


class RuntimeTests(unittest.TestCase):
    def test_list_running_container_names_parses_docker_ps_output(self) -> None:
        with patch(
            "openenv.docker.runtime.subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="alpha\nbeta\n",
                stderr="",
            ),
        ):
            names = list_running_container_names()

        self.assertEqual(names, {"alpha", "beta"})

    def test_fetch_container_logs_returns_stdout(self) -> None:
        with patch(
            "openenv.docker.runtime.subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="line-1\nline-2\n",
                stderr="",
            ),
        ):
            logs = fetch_container_logs("alpha", tail=40)

        self.assertEqual(logs, "line-1\nline-2\n")

    def test_snapshot_installed_skills_reads_skill_files(self) -> None:
        payload = (
            '[{"name": "captured-skill", "files": {'
            '"SKILL.md": "---\\nname: captured-skill\\ndescription: Captured skill\\n'
            'source: acme/captured-skill\\n---\\n", '
            '"templates/report.md": "# Report\\n"}}]'
        )
        with patch(
            "openenv.docker.runtime.subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=payload,
                stderr="",
            ),
        ):
            skills = snapshot_installed_skills("alpha", workspace="/opt/openclaw/workspace")

        self.assertEqual(len(skills), 1)
        self.assertEqual(skills[0].name, "captured-skill")
        self.assertEqual(skills[0].description, "Captured skill")
        self.assertEqual(skills[0].source, "acme/captured-skill")
        self.assertEqual(skills[0].assets, {"templates/report.md": "# Report\n"})

    def test_snapshot_installed_skills_raises_on_invalid_json(self) -> None:
        with patch(
            "openenv.docker.runtime.subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="{not json}",
                stderr="",
            ),
        ):
            with self.assertRaises(CommandError):
                snapshot_installed_skills("alpha", workspace="/opt/openclaw/workspace")

    def test_list_running_container_names_raises_when_docker_is_missing(self) -> None:
        with patch("openenv.docker.runtime.subprocess.run", side_effect=OSError("missing")):
            with self.assertRaises(CommandError) as ctx:
                list_running_container_names()

        self.assertIn("Docker is not available on PATH", str(ctx.exception))

    def test_fetch_container_logs_includes_docker_stderr_on_failure(self) -> None:
        with patch(
            "openenv.docker.runtime.subprocess.run",
            side_effect=subprocess.CalledProcessError(
                returncode=9,
                cmd=["docker", "logs"],
                stderr="permission denied",
            ),
        ):
            with self.assertRaises(CommandError) as ctx:
                fetch_container_logs("alpha")

        self.assertEqual(ctx.exception.exit_code, 9)
        self.assertIn("permission denied", str(ctx.exception))

    def test_snapshot_installed_skills_rejects_non_list_payload(self) -> None:
        with patch(
            "openenv.docker.runtime.subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout='{"name": "wrong"}',
                stderr="",
            ),
        ):
            with self.assertRaises(CommandError) as ctx:
                snapshot_installed_skills("alpha", workspace="/opt/openclaw/workspace")

        self.assertIn("invalid skill snapshot payload", str(ctx.exception))

    def test_snapshot_installed_skills_skips_invalid_entries_and_uses_default_description(self) -> None:
        payload = (
            '[1, {"name": "", "files": {}}, {"name": "broken", "files": {"README.md": "ignored"}}, '
            '{"name": "plain-skill", "files": {"SKILL.md": "No frontmatter\\n", "data.txt": "value"}}]'
        )
        with patch(
            "openenv.docker.runtime.subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=payload,
                stderr="",
            ),
        ):
            skills = snapshot_installed_skills("alpha", workspace="/opt/openclaw/workspace")

        self.assertEqual(len(skills), 1)
        self.assertEqual(skills[0].name, "plain-skill")
        self.assertEqual(
            skills[0].description,
            "Snapshotted skill from running container alpha",
        )
        self.assertIsNone(skills[0].source)
        self.assertEqual(skills[0].assets, {"data.txt": "value"})
