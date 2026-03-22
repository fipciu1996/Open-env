from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from openenv.core.errors import LockResolutionError
from openenv.manifests.loader import load_manifest
from openenv.manifests.lockfile import build_lockfile, dump_lockfile


TESTS_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = TESTS_ROOT / "fixtures"


class LockfileTests(unittest.TestCase):
    def test_lockfile_matches_golden_fixture(self) -> None:
        manifest, raw_manifest_text = load_manifest(FIXTURES / "example.openenv.toml")
        lockfile = build_lockfile(manifest, raw_manifest_text)
        expected = (FIXTURES / "example.openenv.lock").read_text(encoding="utf-8")

        self.assertEqual(dump_lockfile(lockfile), expected)

    def test_lockfile_is_deterministic(self) -> None:
        manifest, raw_manifest_text = load_manifest(FIXTURES / "example.openenv.toml")

        first = dump_lockfile(build_lockfile(manifest, raw_manifest_text))
        second = dump_lockfile(build_lockfile(manifest, raw_manifest_text))

        self.assertEqual(first, second)

    def test_skill_change_updates_manifest_hash(self) -> None:
        manifest, raw_manifest_text = load_manifest(FIXTURES / "example.openenv.toml")
        base_lock = build_lockfile(manifest, raw_manifest_text)
        incident_brief = next(
            skill for skill in manifest.skills if skill.name == "incident-brief"
        )
        incident_brief.content = incident_brief.content + "\n3. Capture action items.\n"

        changed_lock = build_lockfile(manifest, raw_manifest_text)

        self.assertNotEqual(base_lock.manifest_hash, changed_lock.manifest_hash)

    def test_rejects_unpinned_node_requirement(self) -> None:
        manifest, raw_manifest_text = load_manifest(FIXTURES / "example.openenv.toml")
        manifest.runtime.node_packages = ["typescript"]

        with self.assertRaises(LockResolutionError):
            build_lockfile(manifest, raw_manifest_text)

    def test_pulls_missing_local_base_image_before_failing(self) -> None:
        manifest, raw_manifest_text = load_manifest(FIXTURES / "example.openenv.toml")
        manifest.runtime.base_image = "python:3.12-slim"
        digest = "sha256:" + "1" * 64
        with patch("openenv.manifests.lockfile.subprocess.run") as run_mock:
            run_mock.side_effect = [
                subprocess.CalledProcessError(
                    returncode=1,
                    cmd=["docker", "image", "inspect", manifest.runtime.base_image],
                    stderr="Error response from daemon: No such image: python:3.12-slim",
                ),
                subprocess.CompletedProcess(
                    args=["docker", "image", "pull", manifest.runtime.base_image],
                    returncode=0,
                    stdout="Pulled",
                    stderr="",
                ),
                subprocess.CompletedProcess(
                    args=["docker", "image", "inspect", manifest.runtime.base_image],
                    returncode=0,
                    stdout=f'["python@{digest}"]',
                    stderr="",
                ),
            ]

            lockfile = build_lockfile(manifest, raw_manifest_text)

        self.assertEqual(lockfile.base_image["digest"], digest)
        self.assertEqual(
            lockfile.base_image["resolved_reference"],
            f"python:3.12-slim@{digest}",
        )
        self.assertEqual(
            run_mock.call_args_list[1].args[0],
            ["docker", "image", "pull", "python:3.12-slim"],
        )

    def test_preserves_original_tag_when_resolving_local_base_image(self) -> None:
        manifest, raw_manifest_text = load_manifest(FIXTURES / "example.openenv.toml")
        manifest.runtime.base_image = "python:3.12-slim"
        digest = "sha256:" + "2" * 64
        with patch("openenv.manifests.lockfile.subprocess.run") as run_mock:
            run_mock.return_value = subprocess.CompletedProcess(
                args=["docker", "image", "inspect", manifest.runtime.base_image],
                returncode=0,
                stdout=f'["python@{digest}"]',
                stderr="",
            )

            lockfile = build_lockfile(manifest, raw_manifest_text)

        self.assertEqual(
            lockfile.base_image["resolved_reference"],
            f"python:3.12-slim@{digest}",
        )

    def test_reports_pull_failure_when_missing_local_base_image_cannot_be_downloaded(self) -> None:
        manifest, raw_manifest_text = load_manifest(FIXTURES / "example.openenv.toml")
        manifest.runtime.base_image = "python:3.12-slim"
        with patch("openenv.manifests.lockfile.subprocess.run") as run_mock:
            run_mock.side_effect = [
                subprocess.CalledProcessError(
                    returncode=1,
                    cmd=["docker", "image", "inspect", manifest.runtime.base_image],
                    stderr="Error response from daemon: No such image: python:3.12-slim",
                ),
                subprocess.CalledProcessError(
                    returncode=1,
                    cmd=["docker", "image", "pull", manifest.runtime.base_image],
                    stderr="Error response from daemon: pull access denied",
                ),
            ]

            with self.assertRaises(LockResolutionError) as ctx:
                build_lockfile(manifest, raw_manifest_text)

        self.assertIn("docker pull failed", str(ctx.exception))
        self.assertIn("pull access denied", str(ctx.exception))
