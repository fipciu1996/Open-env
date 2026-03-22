from __future__ import annotations

import io
import shutil
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from openenv.bots.manager import (
    BotAnswers,
    DocumentImprovementResult,
    create_bot,
    create_skill_snapshot,
    delete_bot,
    discover_bots,
    discover_running_bots,
    generate_all_bots_stack,
    generate_bot_artifacts,
    improve_bot_markdown_documents,
    interactive_menu,
    load_bot,
    update_bot,
)
from openenv.core.skills import MANDATORY_SKILL_SOURCES
from openenv.docker.runtime import CapturedSkill
from openenv.cli import main
from openenv.manifests.lockfile import build_lockfile as build_lockfile_for_test


TESTS_ROOT = Path(__file__).resolve().parents[1]
TEMP_ROOT = TESTS_ROOT / "_tmp"
TEMP_ROOT.mkdir(exist_ok=True)
PINNED_IMAGE = (
    "python:3.12-slim@sha256:1111111111111111111111111111111111111111111111111111111111111111"
)


class BotManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.work_dir = TEMP_ROOT / "bot-manager"
        if self.work_dir.exists():
            shutil.rmtree(self.work_dir, ignore_errors=True)
        self.work_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.work_dir, ignore_errors=True)

    def test_create_and_discover_bot(self) -> None:
        record = create_bot(
            self.work_dir,
            BotAnswers(
                display_name="Publisher Bot",
                role="Publikacja i dystrybucja tresci",
                skill_sources=["kralsamwise/kdp-publisher"],
                system_packages=["ffmpeg"],
                python_packages=["requests==2.32.3"],
                node_packages=["typescript@5.8.3"],
                secret_names=["OPENAI_API_KEY", "KDP_PASSWORD"],
                websites=["https://kdp.amazon.com"],
                databases=["postgres://publisher-db"],
                access_notes=["Dostep tylko do konta wydawniczego."],
            ),
        )

        self.assertTrue(record.manifest_path.exists())
        text = record.manifest_path.read_text(encoding="utf-8")
        self.assertIn('source = "kralsamwise/kdp-publisher"', text)
        for source in MANDATORY_SKILL_SOURCES:
            self.assertIn(f'source = "{source}"', text)
        self.assertIn("[access]", text)
        self.assertNotIn("[[runtime.secret_refs]]", text)
        self.assertIn('node_packages = ["typescript@5.8.3"]', text)
        self.assertIn('agents_md = "AGENTS.md"', text)
        self.assertIn('soul_md = "SOUL.md"', text)
        self.assertIn('user_md = "USER.md"', text)
        self.assertIn('identity_md = "IDENTITY.md"', text)
        self.assertIn('tools_md = "TOOLS.md"', text)
        self.assertIn('memory_seed = "memory.md"', text)
        self.assertNotIn("# Agent Contract", text)
        self.assertTrue((self.work_dir / "bots" / "publisher-bot" / "AGENTS.md").exists())
        self.assertTrue((self.work_dir / "bots" / "publisher-bot" / "SOUL.md").exists())
        self.assertTrue((self.work_dir / "bots" / "publisher-bot" / "USER.md").exists())
        self.assertTrue((self.work_dir / "bots" / "publisher-bot" / "IDENTITY.md").exists())
        self.assertTrue((self.work_dir / "bots" / "publisher-bot" / "TOOLS.md").exists())
        self.assertTrue((self.work_dir / "bots" / "publisher-bot" / "memory.md").exists())
        sidecar_env = (self.work_dir / "bots" / "publisher-bot" / ".env").read_text(
            encoding="utf-8"
        )
        self.assertIn("OPENAI_API_KEY=", sidecar_env)
        self.assertIn("KDP_PASSWORD=", sidecar_env)

        discovered = discover_bots(self.work_dir)
        self.assertEqual(len(discovered), 1)
        self.assertEqual(discovered[0].display_name, "Publisher Bot")
        self.assertEqual(discovered[0].role, "Publikacja i dystrybucja tresci")
        self.assertEqual(
            [
                skill.source
                for skill in discovered[0].manifest.skills[
                    : len(MANDATORY_SKILL_SOURCES)
                ]
            ],
            list(MANDATORY_SKILL_SOURCES),
        )
        self.assertEqual(
            [secret.name for secret in discovered[0].manifest.runtime.secret_refs],
            ["OPENAI_API_KEY", "KDP_PASSWORD"],
        )

    def test_update_bot_can_rename_and_replace_manifest_data(self) -> None:
        create_bot(
            self.work_dir,
            BotAnswers(
                display_name="Publisher Bot",
                role="Publikacja tresci",
                skill_sources=["kralsamwise/kdp-publisher"],
                system_packages=["ffmpeg"],
                python_packages=["requests==2.32.3"],
                node_packages=["typescript@5.8.3"],
                secret_names=["OPENAI_API_KEY"],
                websites=["https://kdp.amazon.com"],
                databases=["postgres://publisher-db"],
                access_notes=["Read only"],
            ),
        )
        env_path = self.work_dir / "bots" / "publisher-bot" / ".env"
        env_path.write_text(
            "# Secret references for Publisher Bot\n"
            "# Keys declared here are synthesized into runtime.secret_refs for the bot.\n\n"
            "OPENAI_API_KEY=already-set\n",
            encoding="utf-8",
        )

        updated = update_bot(
            self.work_dir,
            "publisher-bot",
            BotAnswers(
                display_name="Analytics Bot",
                role="Analiza i raportowanie",
                skill_sources=["kralsamwise/kdp-publisher", "acme/report-writer"],
                system_packages=["jq"],
                python_packages=["pandas==2.2.3"],
                node_packages=["tsx@4.19.3"],
                secret_names=["OPENAI_API_KEY", "ANALYTICS_TOKEN"],
                websites=["https://analytics.example.com"],
                databases=["postgres://analytics-db"],
                access_notes=["Write access only in reporting schema"],
            ),
        )

        self.assertEqual(updated.slug, "analytics-bot")
        self.assertFalse((self.work_dir / "bots" / "publisher-bot").exists())
        self.assertTrue((self.work_dir / "bots" / "analytics-bot").exists())

        text = updated.manifest_path.read_text(encoding="utf-8")
        self.assertIn('agent_name = "Analytics Bot"', text)
        self.assertIn('source = "acme/report-writer"', text)
        self.assertIn('"jq"', text)
        self.assertIn('"pandas==2.2.3"', text)
        self.assertNotIn("[[runtime.secret_refs]]", text)
        self.assertIn('node_packages = ["tsx@4.19.3"]', text)
        self.assertIn('agents_md = "AGENTS.md"', text)
        self.assertTrue((self.work_dir / "bots" / "analytics-bot" / "AGENTS.md").exists())
        self.assertTrue((self.work_dir / "bots" / "analytics-bot" / "memory.md").exists())

        updated_env = (self.work_dir / "bots" / "analytics-bot" / ".env").read_text(
            encoding="utf-8"
        )
        self.assertIn("OPENAI_API_KEY=already-set", updated_env)
        self.assertIn("ANALYTICS_TOKEN=", updated_env)

    def test_delete_bot_removes_directory(self) -> None:
        record = create_bot(
            self.work_dir,
            BotAnswers(
                display_name="Cleanup Bot",
                role="Czyszczenie danych",
                skill_sources=[],
                system_packages=[],
                python_packages=[],
                node_packages=[],
                secret_names=[],
                websites=[],
                databases=[],
                access_notes=[],
            ),
        )
        self.assertEqual(
            [skill.source for skill in record.manifest.skills],
            list(MANDATORY_SKILL_SOURCES),
        )

        delete_bot(self.work_dir, "cleanup-bot")

        self.assertEqual(discover_bots(self.work_dir), [])

    def test_generate_bot_artifacts_writes_bundle(self) -> None:
        create_bot(
            self.work_dir,
            BotAnswers(
                display_name="Bundle Bot",
                role="Generowanie artefaktow",
                skill_sources=["kralsamwise/kdp-publisher"],
                system_packages=[],
                python_packages=["requests==2.32.3"],
                node_packages=["typescript@5.8.3"],
                secret_names=["OPENAI_API_KEY"],
                websites=[],
                databases=[],
                access_notes=[],
            ),
        )

        with patch(
            "openenv.bots.manager.build_lockfile",
            side_effect=self._build_stub_lockfile,
        ):
            artifacts = generate_bot_artifacts(self.work_dir, "bundle-bot")

        self.assertTrue(artifacts.lock_path.exists())
        self.assertTrue(artifacts.dockerfile_path.exists())
        self.assertTrue(artifacts.compose_path.exists())
        self.assertTrue(artifacts.env_path.exists())
        self.assertEqual(artifacts.image_tag, "openenv/bundle-bot:0.1.0")
        self.assertIn(
            "# syntax=docker/dockerfile:1",
            artifacts.dockerfile_path.read_text(encoding="utf-8"),
        )
        self.assertIn(
            "docker-compose-bundle-bot.yml",
            str(artifacts.compose_path),
        )
        self.assertIn(
            "# OpenClaw runtime and secrets for Bundle Bot",
            artifacts.env_path.read_text(encoding="utf-8"),
        )
        self.assertIn(
            "OPENAI_API_KEY=",
            artifacts.env_path.read_text(encoding="utf-8"),
        )

    def test_generate_all_bots_stack_writes_shared_compose(self) -> None:
        create_bot(
            self.work_dir,
            BotAnswers(
                display_name="Bundle Bot",
                role="Generowanie artefaktow",
                skill_sources=["kralsamwise/kdp-publisher"],
                system_packages=[],
                python_packages=["requests==2.32.3"],
                node_packages=["typescript@5.8.3"],
                secret_names=["OPENAI_API_KEY"],
                websites=[],
                databases=[],
                access_notes=[],
            ),
        )
        create_bot(
            self.work_dir,
            BotAnswers(
                display_name="Docs Bot",
                role="Improving documentation",
                skill_sources=[],
                system_packages=[],
                python_packages=[],
                node_packages=[],
                secret_names=[],
                websites=[],
                databases=[],
                access_notes=[],
            ),
        )

        with patch(
            "openenv.bots.manager.build_lockfile",
            side_effect=self._build_stub_lockfile,
        ):
            stack = generate_all_bots_stack(self.work_dir)

        self.assertEqual(len(stack.bot_artifacts), 2)
        self.assertTrue(stack.stack_path.exists())
        stack_text = stack.stack_path.read_text(encoding="utf-8")
        self.assertIn("openclaw-gateway:", stack_text)
        self.assertEqual(stack_text.count("openclaw-gateway:"), 1)
        self.assertIn("bot-bundle-bot:", stack_text)
        self.assertIn("bot-docs-bot:", stack_text)
        self.assertIn('context: "./bundle-bot"', stack_text)
        self.assertIn('context: "./docs-bot"', stack_text)

    def test_interactive_menu_adds_edits_and_deletes_bot(self) -> None:
        answers = iter(
            [
                "pl",
                "2",
                "Menu Bot",
                "Obsluga publikacji",
                "kralsamwise/kdp-publisher",
                "imagemagick",
                "",
                "typescript@5.8.3",
                "OPENAI_API_KEY",
                "https://example.com",
                "publisher-db",
                "Dostep tylko do produkcji",
                "3",
                "1",
                "Menu Bot 2",
                "Obsluga raportowania",
                "kralsamwise/kdp-publisher, acme/report-writer",
                "jq",
                "pandas==2.2.3",
                "tsx@4.19.3",
                "OPENAI_API_KEY, REPORT_TOKEN",
                "https://reports.example.com",
                "reporting-db",
                "Tylko raporty",
                "4",
                "1",
                "t",
                "6",
            ]
        )
        stdout = io.StringIO()
        with patch("builtins.input", side_effect=lambda _: next(answers)):
            with redirect_stdout(stdout):
                exit_code = interactive_menu(self.work_dir)

        self.assertEqual(exit_code, 0)
        output = stdout.getvalue()
        self.assertIn("Utworzono bota `Menu Bot`", output)
        self.assertIn("Zaktualizowano bota `Menu Bot 2`", output)
        self.assertIn("Usunieto bota `Menu Bot 2`.", output)
        self.assertEqual(discover_bots(self.work_dir), [])

    def test_interactive_list_can_generate_artifacts_for_selected_bot(self) -> None:
        create_bot(
            self.work_dir,
            BotAnswers(
                display_name="Export Bot",
                role="Eksport artefaktow",
                skill_sources=["kralsamwise/kdp-publisher"],
                system_packages=[],
                python_packages=[],
                node_packages=["typescript@5.8.3"],
                secret_names=["OPENAI_API_KEY"],
                websites=[],
                databases=[],
                access_notes=[],
            ),
        )

        answers = iter(["en", "1", "1", "1", "6"])
        stdout = io.StringIO()
        with patch(
            "openenv.bots.manager.build_lockfile",
            side_effect=self._build_stub_lockfile,
        ):
            with patch("builtins.input", side_effect=lambda _: next(answers)):
                with redirect_stdout(stdout):
                    exit_code = interactive_menu(self.work_dir)

        self.assertEqual(exit_code, 0)
        output = stdout.getvalue()
        self.assertIn("Open-env - Interactive menu", output)
        self.assertIn("Registered bots:", output)
        self.assertIn("Generated Dockerfile:", output)
        self.assertIn("Generated docker-compose:", output)
        self.assertTrue((self.work_dir / "bots" / "export-bot" / "Dockerfile").exists())
        self.assertTrue(
            (self.work_dir / "bots" / "export-bot" / "docker-compose-export-bot.yml").exists()
        )

    def test_interactive_list_can_generate_shared_stack_for_all_bots(self) -> None:
        create_bot(
            self.work_dir,
            BotAnswers(
                display_name="Export Bot",
                role="Eksport artefaktow",
                skill_sources=["kralsamwise/kdp-publisher"],
                system_packages=[],
                python_packages=[],
                node_packages=["typescript@5.8.3"],
                secret_names=["OPENAI_API_KEY"],
                websites=[],
                databases=[],
                access_notes=[],
            ),
        )
        create_bot(
            self.work_dir,
            BotAnswers(
                display_name="Docs Bot",
                role="Improving documentation",
                skill_sources=[],
                system_packages=[],
                python_packages=[],
                node_packages=[],
                secret_names=[],
                websites=[],
                databases=[],
                access_notes=[],
            ),
        )

        answers = iter(["en", "1", "a", "6"])
        stdout = io.StringIO()
        with patch(
            "openenv.bots.manager.build_lockfile",
            side_effect=self._build_stub_lockfile,
        ):
            with patch("builtins.input", side_effect=lambda _: next(answers)):
                with redirect_stdout(stdout):
                    exit_code = interactive_menu(self.work_dir)

        self.assertEqual(exit_code, 0)
        output = stdout.getvalue()
        self.assertIn("A. Generate a shared stack for all bots", output)
        self.assertIn("Generated shared stack:", output)
        self.assertTrue((self.work_dir / "bots" / "all-bots-compose.yml").exists())

    def test_improve_bot_markdown_documents_updates_files(self) -> None:
        create_bot(
            self.work_dir,
            BotAnswers(
                display_name="Docs Bot",
                role="Improving documentation",
                skill_sources=["kralsamwise/kdp-publisher"],
                system_packages=[],
                python_packages=[],
                node_packages=[],
                secret_names=[],
                websites=[],
                databases=[],
                access_notes=[],
            ),
        )

        def fake_openrouter_call(**kwargs):
            kwargs["write_document"]("AGENTS.md", "# Updated contract\n")
            kwargs["write_document"]("memory.md", "Keep context fresh.\n")
            return "Updated two files."

        with patch(
            "openenv.bots.manager.improve_markdown_documents_with_openrouter",
            side_effect=fake_openrouter_call,
        ):
            result = improve_bot_markdown_documents(
                self.work_dir,
                "docs-bot",
                instruction="Refresh the docs.",
                api_key="test-key",
            )

        self.assertEqual(result.summary, "Updated two files.")
        self.assertEqual(len(result.updated_paths), 2)
        self.assertEqual(
            (self.work_dir / "bots" / "docs-bot" / "AGENTS.md").read_text(
                encoding="utf-8"
            ),
            "# Updated contract\n",
        )
        self.assertEqual(
            (self.work_dir / "bots" / "docs-bot" / "memory.md").read_text(
                encoding="utf-8"
            ),
            "Keep context fresh.\n",
        )

    def test_interactive_list_can_improve_docs_and_create_root_env_key(self) -> None:
        create_bot(
            self.work_dir,
            BotAnswers(
                display_name="Docs Bot",
                role="Improving documentation",
                skill_sources=["kralsamwise/kdp-publisher"],
                system_packages=[],
                python_packages=[],
                node_packages=[],
                secret_names=[],
                websites=[],
                databases=[],
                access_notes=[],
            ),
        )

        answers = iter(["en", "1", "1", "2", "", "6"])
        stdout = io.StringIO()
        with patch(
            "openenv.bots.manager.improve_bot_markdown_documents",
            return_value=DocumentImprovementResult(
                bot=load_bot(self.work_dir, "docs-bot"),
                summary="Updated docs.",
                updated_paths=[self.work_dir / "bots" / "docs-bot" / "AGENTS.md"],
            ),
        ) as improve_docs:
            with patch("openenv.bots.manager.getpass", return_value="root-openrouter-key"):
                with patch("builtins.input", side_effect=lambda _: next(answers)):
                    with redirect_stdout(stdout):
                        exit_code = interactive_menu(self.work_dir)

        self.assertEqual(exit_code, 0)
        improve_docs.assert_called_once()
        self.assertEqual(improve_docs.call_args.kwargs["api_key"], "root-openrouter-key")
        root_env = (self.work_dir / ".env").read_text(encoding="utf-8")
        self.assertIn("OPENROUTER_API_KEY=root-openrouter-key", root_env)
        output = stdout.getvalue()
        self.assertIn("OPENROUTER_API_KEY was not found", output)
        self.assertIn("Saved OPENROUTER_API_KEY", output)
        self.assertIn("OpenRouter finished improving the documents", output)

    def test_discover_running_bots_returns_only_running_managed_bots(self) -> None:
        create_bot(
            self.work_dir,
            BotAnswers(
                display_name="Running Bot",
                role="Monitoring runtime",
                skill_sources=[],
                system_packages=[],
                python_packages=[],
                node_packages=[],
                secret_names=[],
                websites=[],
                databases=[],
                access_notes=[],
            ),
        )
        create_bot(
            self.work_dir,
            BotAnswers(
                display_name="Stopped Bot",
                role="Idle runtime",
                skill_sources=[],
                system_packages=[],
                python_packages=[],
                node_packages=[],
                secret_names=[],
                websites=[],
                databases=[],
                access_notes=[],
            ),
        )
        with patch(
            "openenv.bots.manager.build_lockfile",
            side_effect=self._build_stub_lockfile,
        ):
            generate_bot_artifacts(self.work_dir, "running-bot")
            generate_bot_artifacts(self.work_dir, "stopped-bot")

        with patch(
            "openenv.bots.manager.list_running_container_names",
            return_value={"running-bot-openclaw-gateway"},
        ):
            running_bots = discover_running_bots(self.work_dir)

        self.assertEqual([bot.slug for bot in running_bots], ["running-bot"])

    def test_create_skill_snapshot_adds_new_skill_and_updates_lockfile(self) -> None:
        create_bot(
            self.work_dir,
            BotAnswers(
                display_name="Snapshot Bot",
                role="Runtime snapshotting",
                skill_sources=[],
                system_packages=[],
                python_packages=[],
                node_packages=[],
                secret_names=[],
                websites=[],
                databases=[],
                access_notes=[],
            ),
        )
        with patch(
            "openenv.bots.manager.build_lockfile",
            side_effect=self._build_stub_lockfile,
        ):
            generate_bot_artifacts(self.work_dir, "snapshot-bot")

        with patch(
            "openenv.bots.manager.list_running_container_names",
            return_value={"snapshot-bot-openclaw-gateway"},
        ):
            with patch(
                "openenv.bots.manager.snapshot_installed_skills",
                return_value=[
                    CapturedSkill(
                        name="extra-skill",
                        description="Captured at runtime",
                        content=(
                            "---\n"
                            "name: extra-skill\n"
                            "description: Captured at runtime\n"
                            "source: acme/extra-skill\n"
                            "---\n"
                        ),
                        source="acme/extra-skill",
                        assets={"templates/note.md": "# Snapshot\n"},
                    )
                ],
            ):
                result = create_skill_snapshot(self.work_dir, "snapshot-bot")

        self.assertEqual(result.added_skill_names, ["extra-skill"])
        self.assertIsNotNone(result.lock_path)
        manifest_text = (self.work_dir / "bots" / "snapshot-bot" / "openenv.toml").read_text(
            encoding="utf-8"
        )
        self.assertIn('name = "extra-skill"', manifest_text)
        self.assertIn('source = "acme/extra-skill"', manifest_text)
        self.assertTrue((self.work_dir / "bots" / "snapshot-bot" / "openenv.lock").exists())

    def test_interactive_running_bots_can_show_logs(self) -> None:
        create_bot(
            self.work_dir,
            BotAnswers(
                display_name="Logs Bot",
                role="Reading logs",
                skill_sources=[],
                system_packages=[],
                python_packages=[],
                node_packages=[],
                secret_names=[],
                websites=[],
                databases=[],
                access_notes=[],
            ),
        )
        with patch(
            "openenv.bots.manager.build_lockfile",
            side_effect=self._build_stub_lockfile,
        ):
            generate_bot_artifacts(self.work_dir, "logs-bot")

        answers = iter(["en", "5", "1", "1", "6"])
        stdout = io.StringIO()
        with patch(
            "openenv.bots.manager.list_running_container_names",
            return_value={"logs-bot-openclaw-gateway"},
        ):
            with patch(
                "openenv.bots.manager.fetch_container_logs",
                return_value="alpha\nbeta\n",
            ):
                with patch("builtins.input", side_effect=lambda _: next(answers)):
                    with redirect_stdout(stdout):
                        exit_code = interactive_menu(self.work_dir)

        self.assertEqual(exit_code, 0)
        output = stdout.getvalue()
        self.assertIn("Running bots:", output)
        self.assertIn("Logs for `Logs Bot`:", output)
        self.assertIn("alpha", output)

    def test_main_without_args_opens_interactive_menu(self) -> None:
        with patch("openenv.cli.interactive_menu", return_value=0) as menu:
            exit_code = main([])

        self.assertEqual(exit_code, 0)
        menu.assert_called_once()

    def _build_stub_lockfile(self, manifest, raw_manifest_text):
        return build_lockfile_for_test(
            manifest,
            raw_manifest_text,
            resolver=lambda _: {
                "digest": PINNED_IMAGE.split("@", 1)[1],
                "resolved_reference": PINNED_IMAGE,
            },
        )
