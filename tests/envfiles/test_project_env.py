from __future__ import annotations

import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

from openenv.core.errors import ValidationError
from openenv.envfiles.project_env import (
    get_project_env_value,
    load_project_env,
    parse_project_env_text,
    project_env_path,
    upsert_project_env_text,
    write_project_env_value,
)


TESTS_ROOT = Path(__file__).resolve().parents[1]
TEMP_ROOT = TESTS_ROOT / "_tmp"
TEMP_ROOT.mkdir(exist_ok=True)


class ProjectEnvTests(unittest.TestCase):
    def setUp(self) -> None:
        self.work_dir = TEMP_ROOT / "project-env"
        if self.work_dir.exists():
            shutil.rmtree(self.work_dir, ignore_errors=True)
        self.work_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.work_dir, ignore_errors=True)

    def test_project_env_path_uses_root_directory(self) -> None:
        self.assertEqual(project_env_path(self.work_dir), self.work_dir / ".env")

    def test_load_project_env_returns_empty_for_missing_file(self) -> None:
        self.assertEqual(load_project_env(self.work_dir / ".env"), {})

    def test_get_project_env_value_prefers_os_env_over_file(self) -> None:
        env_path = self.work_dir / ".env"
        env_path.write_text("OPENROUTER_API_KEY=from-file\n", encoding="utf-8")

        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "from-os"}, clear=False):
            value = get_project_env_value(self.work_dir, "OPENROUTER_API_KEY")

        self.assertEqual(value, "from-os")

    def test_write_project_env_value_creates_and_updates_env_file(self) -> None:
        first_path = write_project_env_value(self.work_dir, "OPENROUTER_API_KEY", "secret-1")
        second_path = write_project_env_value(self.work_dir, "OPENROUTER_API_KEY", "secret-2")
        third_path = write_project_env_value(self.work_dir, "ANOTHER_KEY", "value-3")

        self.assertEqual(first_path, self.work_dir / ".env")
        self.assertEqual(second_path, self.work_dir / ".env")
        self.assertEqual(third_path.read_text(encoding="utf-8"), "OPENROUTER_API_KEY=secret-2\n\nANOTHER_KEY=value-3\n")

    def test_write_project_env_value_rejects_invalid_key(self) -> None:
        with self.assertRaises(ValidationError):
            write_project_env_value(self.work_dir, "INVALID-KEY", "value")

    def test_parse_project_env_text_rejects_invalid_lines(self) -> None:
        cases = [
            ("OPENROUTER_API_KEY", "sample.env:1 must use KEY=VALUE syntax."),
            ("1KEY=value", "sample.env:1 has an invalid env var name: '1KEY'"),
            ("KEY=value\nKEY=other", "sample.env:2 duplicates env var KEY."),
        ]

        for text, expected in cases:
            with self.subTest(text=text):
                with self.assertRaises(ValidationError) as ctx:
                    parse_project_env_text(text, label="sample.env")
                self.assertEqual(str(ctx.exception), expected)

    def test_upsert_project_env_text_preserves_comments_and_replaces_existing_value(self) -> None:
        original = "# comment\nOPENROUTER_API_KEY=old\n"

        rendered = upsert_project_env_text(original, "OPENROUTER_API_KEY", "new")
        appended = upsert_project_env_text("# comment\n", "ANOTHER_KEY", "value")

        self.assertEqual(rendered, "# comment\nOPENROUTER_API_KEY=new\n")
        self.assertEqual(appended, "# comment\n\nANOTHER_KEY=value\n")
