from __future__ import annotations

import io
import json
import urllib.error
import unittest
from unittest.mock import patch

from openenv.core.errors import OpenEnvError
from openenv.integrations.openrouter import (
    _apply_document_updates,
    _assistant_text,
    _decode_tool_arguments,
    _openrouter_chat_completion,
    improve_markdown_documents_with_openrouter,
)


class _FakeResponse:
    def __init__(self, payload: dict[str, object]):
        self._payload = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def read(self) -> bytes:
        return self._payload


class OpenRouterTests(unittest.TestCase):
    def test_tool_calling_flow_reads_context_and_writes_documents(self) -> None:
        writes: dict[str, str] = {}
        responses = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "get_bot_context", "arguments": "{}"},
                    }
                ],
            },
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_2",
                        "type": "function",
                        "function": {
                            "name": "write_bot_documents",
                            "arguments": (
                                '{"updates": [{"file": "AGENTS.md", "content": "# Better contract\\n"}, '
                                '{"file": "memory.md", "content": "Keep focus.\\n"}]}'
                            ),
                        },
                    }
                ],
            },
            {"role": "assistant", "content": "Updated AGENTS.md and memory.md."},
        ]

        with patch(
            "openenv.integrations.openrouter._openrouter_chat_completion",
            side_effect=responses,
        ) as chat_completion:
            summary = improve_markdown_documents_with_openrouter(
                api_key="test-key",
                bot_name="Example Bot",
                context_payload={
                    "bot": {"name": "Example Bot"},
                    "documents": {
                        "AGENTS.md": "# Agent Contract\n",
                        "memory.md": "Remember context.\n",
                    },
                },
                instruction="Improve both files.",
                write_document=lambda name, content: writes.__setitem__(name, content),
            )

        self.assertEqual(summary, "Updated AGENTS.md and memory.md.")
        self.assertEqual(
            writes,
            {
                "AGENTS.md": "# Better contract\n",
                "memory.md": "Keep focus.\n",
            },
        )
        self.assertEqual(chat_completion.call_count, 3)
        first_call_messages = chat_completion.call_args_list[0].kwargs["messages"]
        self.assertIn(
            "All resulting markdown files must be written in English.",
            first_call_messages[0]["content"],
        )
        self.assertIn(
            "The final versions of every markdown document must be consistently written in English.",
            first_call_messages[1]["content"],
        )

    def test_rejects_disallowed_file_update(self) -> None:
        with patch(
            "openenv.integrations.openrouter._openrouter_chat_completion",
            return_value={
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "write_bot_documents",
                            "arguments": (
                                '{"updates": [{"file": "secrets.txt", "content": "nope"}]}'
                            ),
                        },
                    }
                ],
            },
        ):
            with self.assertRaises(OpenEnvError):
                improve_markdown_documents_with_openrouter(
                    api_key="test-key",
                    bot_name="Example Bot",
                    context_payload={
                        "bot": {"name": "Example Bot"},
                        "documents": {"AGENTS.md": "# Agent Contract\n"},
                    },
                    instruction="Break the rules.",
                    write_document=lambda *_: None,
                )

    def test_openrouter_chat_completion_reports_http_error_detail(self) -> None:
        http_error = urllib.error.HTTPError(
            url="https://openrouter.ai",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=io.BytesIO(b'{"error":"bad key"}'),
        )
        with patch("urllib.request.urlopen", side_effect=http_error):
            with self.assertRaises(OpenEnvError) as ctx:
                _openrouter_chat_completion(
                    api_key="bad-key",
                    model="demo-model",
                    messages=[],
                    tools=[],
                )

        self.assertIn("HTTP 401", str(ctx.exception))
        self.assertIn("bad key", str(ctx.exception))

    def test_openrouter_chat_completion_reports_network_errors(self) -> None:
        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("offline"),
        ):
            with self.assertRaises(OpenEnvError) as ctx:
                _openrouter_chat_completion(
                    api_key="key",
                    model="demo-model",
                    messages=[],
                    tools=[],
                )

        self.assertIn("OpenRouter is not reachable: offline", str(ctx.exception))

    def test_openrouter_chat_completion_rejects_unexpected_payload(self) -> None:
        with patch("urllib.request.urlopen", return_value=_FakeResponse({"choices": []})):
            with self.assertRaises(OpenEnvError) as ctx:
                _openrouter_chat_completion(
                    api_key="key",
                    model="demo-model",
                    messages=[],
                    tools=[],
                )

        self.assertIn("unexpected response payload", str(ctx.exception))

    def test_assistant_text_extracts_text_fragments_from_content_list(self) -> None:
        text = _assistant_text(
            {
                "content": [
                    {"type": "text", "text": "First line"},
                    {"type": "image", "url": "ignored"},
                    {"type": "text", "text": "Second line"},
                ]
            }
        )

        self.assertEqual(text, "First line\nSecond line")

    def test_decode_tool_arguments_requires_valid_json_object(self) -> None:
        with self.assertRaises(OpenEnvError):
            _decode_tool_arguments("{not-json}")
        with self.assertRaises(OpenEnvError):
            _decode_tool_arguments('["not", "an", "object"]')

    def test_improve_documents_uses_batch_processing_for_larger_sets(self) -> None:
        writes: dict[str, str] = {}
        responses = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "batch1-call1",
                        "type": "function",
                        "function": {"name": "get_bot_context", "arguments": "{}"},
                    }
                ],
            },
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "batch1-call2",
                        "type": "function",
                        "function": {
                            "name": "write_bot_documents",
                            "arguments": (
                                '{"updates": ['
                                '{"file": "AGENTS.md", "content": "# Batch one\\n"}, '
                                '{"file": "IDENTITY.md", "content": "# Identity\\n"}'
                                "]}"
                            ),
                        },
                    }
                ],
            },
            {"role": "assistant", "content": "Updated the first batch."},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "batch2-call1",
                        "type": "function",
                        "function": {"name": "get_bot_context", "arguments": "{}"},
                    }
                ],
            },
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "batch2-call2",
                        "type": "function",
                        "function": {
                            "name": "write_bot_documents",
                            "arguments": (
                                '{"updates": ['
                                '{"file": "memory.md", "content": "Keep the context fresh.\\n"}'
                                "]}"
                            ),
                        },
                    }
                ],
            },
            {"role": "assistant", "content": "Updated the final batch."},
        ]

        with patch(
            "openenv.integrations.openrouter._openrouter_chat_completion",
            side_effect=responses,
        ) as chat_completion:
            summary = improve_markdown_documents_with_openrouter(
                api_key="test-key",
                bot_name="Example Bot",
                context_payload={
                    "bot": {"name": "Example Bot"},
                    "documents": {
                        "AGENTS.md": "# Agent Contract\n",
                        "IDENTITY.md": "# Identity\n",
                        "memory.md": "Remember context.\n",
                    },
                },
                instruction="Improve all docs.",
                write_document=lambda name, content: writes.__setitem__(name, content),
                batch_size=2,
            )

        self.assertEqual(
            summary,
            "Batch 1: Updated the first batch. | Batch 2: Updated the final batch.",
        )
        self.assertEqual(chat_completion.call_count, 6)
        self.assertEqual(
            writes,
            {
                "AGENTS.md": "# Batch one\n",
                "IDENTITY.md": "# Identity\n",
                "memory.md": "Keep the context fresh.\n",
            },
        )
        first_batch_enum = chat_completion.call_args_list[0].kwargs["tools"][1]["function"][
            "parameters"
        ]["properties"]["updates"]["items"]["properties"]["file"]["enum"]
        second_batch_enum = chat_completion.call_args_list[3].kwargs["tools"][1]["function"][
            "parameters"
        ]["properties"]["updates"]["items"]["properties"]["file"]["enum"]
        self.assertEqual(first_batch_enum, ["AGENTS.md", "IDENTITY.md"])
        self.assertEqual(second_batch_enum, ["memory.md"])
        self.assertIn(
            "You are processing batch 1 of 2. Only update these files in this batch: AGENTS.md, IDENTITY.md.",
            chat_completion.call_args_list[0].kwargs["messages"][0]["content"],
        )

    def test_apply_document_updates_rejects_invalid_updates(self) -> None:
        with self.assertRaises(OpenEnvError):
            _apply_document_updates(
                {"updates": "bad"},
                allowed_files=["AGENTS.md"],
                write_document=lambda *_: None,
            )
        with self.assertRaises(OpenEnvError):
            _apply_document_updates(
                {"updates": [123]},
                allowed_files=["AGENTS.md"],
                write_document=lambda *_: None,
            )
        with self.assertRaises(OpenEnvError):
            _apply_document_updates(
                {"updates": [{"file": "AGENTS.md", "content": "   "}]},
                allowed_files=["AGENTS.md"],
                write_document=lambda *_: None,
            )
