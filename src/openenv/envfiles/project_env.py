"""Helpers for loading and updating the project root .env file."""

from __future__ import annotations

import os
import re
from pathlib import Path

from openenv.core.errors import ValidationError


PROJECT_ENV_FILENAME = ".env"
_ENV_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def project_env_path(root: str | Path) -> Path:
    """Return the project-level .env path."""
    return Path(root).resolve() / PROJECT_ENV_FILENAME


def load_project_env(path: str | Path) -> dict[str, str]:
    """Load KEY=VALUE pairs from a project .env file."""
    env_path = Path(path)
    if not env_path.exists():
        return {}
    return dict(parse_project_env_text(env_path.read_text(encoding="utf-8"), label=str(env_path)))


def get_project_env_value(root: str | Path, key: str) -> str | None:
    """Resolve a configuration value from the OS env first, then the project .env."""
    if value := os.environ.get(key):
        return value
    return load_project_env(project_env_path(root)).get(key)


def write_project_env_value(root: str | Path, key: str, value: str) -> Path:
    """Upsert a single KEY=VALUE entry in the project root .env file."""
    if not _ENV_KEY_PATTERN.match(key):
        raise ValidationError(f"Invalid env var name: {key!r}")
    env_path = project_env_path(root)
    existing_text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    rendered = upsert_project_env_text(existing_text, key, value)
    env_path.write_text(rendered, encoding="utf-8")
    return env_path


def parse_project_env_text(text: str, *, label: str) -> list[tuple[str, str]]:
    """Parse a project .env file."""
    entries: list[tuple[str, str]] = []
    seen: set[str] = set()
    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in raw_line:
            raise ValidationError(f"{label}:{line_no} must use KEY=VALUE syntax.")
        key, value = raw_line.split("=", 1)
        key = key.strip()
        if not _ENV_KEY_PATTERN.match(key):
            raise ValidationError(
                f"{label}:{line_no} has an invalid env var name: {key!r}"
            )
        if key in seen:
            raise ValidationError(f"{label}:{line_no} duplicates env var {key}.")
        seen.add(key)
        entries.append((key, value))
    return entries


def upsert_project_env_text(text: str, key: str, value: str) -> str:
    """Insert or replace a KEY=VALUE line while preserving other content."""
    lines = text.splitlines()
    rendered_line = f"{key}={value}"
    updated = False
    result: list[str] = []
    for raw_line in lines:
        stripped = raw_line.strip()
        if stripped and not stripped.startswith("#") and "=" in raw_line:
            current_key, _ = raw_line.split("=", 1)
            if current_key.strip() == key:
                result.append(rendered_line)
                updated = True
                continue
        result.append(raw_line)
    if not updated:
        if result and result[-1] != "":
            result.append("")
        result.append(rendered_line)
    return "\n".join(result).rstrip() + "\n"
