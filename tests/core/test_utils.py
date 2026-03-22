from __future__ import annotations

import unittest

from openenv.core.utils import rewrite_openclaw_home_paths


class UtilsTests(unittest.TestCase):
    def test_rewrite_openclaw_home_paths_rewrites_known_home_aliases(self) -> None:
        text = "\n".join(
            [
                "/home/deus/.openclaw/workspace/memory/projects/demo.md",
                "/root/.openclaw/openclaw.json",
                "$HOME/.openclaw/cache.db",
                "${HOME}/.openclaw/workspace/logs/session.json",
                "~/.openclaw/settings.json",
            ]
        )

        rewritten = rewrite_openclaw_home_paths(
            text,
            state_dir="/opt/openclaw",
            workspace="/opt/openclaw/workspace",
        )

        self.assertIn("/opt/openclaw/workspace/memory/projects/demo.md", rewritten)
        self.assertIn("/opt/openclaw/openclaw.json", rewritten)
        self.assertIn("/opt/openclaw/cache.db", rewritten)
        self.assertIn("/opt/openclaw/workspace/logs/session.json", rewritten)
        self.assertIn("/opt/openclaw/settings.json", rewritten)
        self.assertNotIn("/home/deus/.openclaw", rewritten)
        self.assertNotIn("$HOME/.openclaw", rewritten)
        self.assertNotIn("${HOME}/.openclaw", rewritten)
        self.assertNotIn("~/.openclaw", rewritten)
