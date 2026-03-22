"""Helpers for sidecar .env secret reference files."""

from __future__ import annotations

import re
from pathlib import Path

from openenv.core.errors import ValidationError
from openenv.core.models import SecretRef


BOT_SECRET_ENV_FILENAME = ".env"
_ENV_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def secret_env_path(directory: str | Path) -> Path:
    """Return the canonical sidecar env path for a manifest directory."""
    return Path(directory) / BOT_SECRET_ENV_FILENAME


def load_secret_values(path: str | Path) -> dict[str, str]:
    """Load env key/value pairs from a sidecar .env file."""
    env_path = Path(path)
    if not env_path.exists():
        return {}
    return dict(parse_secret_env_text(env_path.read_text(encoding="utf-8"), label=str(env_path)))


def load_secret_refs(path: str | Path) -> list[SecretRef]:
    """Load secret refs from a sidecar .env file."""
    return [
        SecretRef(name=name, source=f"env:{name}", required=True)
        for name in load_secret_values(path)
    ]


def render_secret_env(
    secret_names: list[str],
    *,
    existing_values: dict[str, str] | None = None,
    display_name: str | None = None,
) -> str:
    """Render the canonical bot .env file."""
    values = existing_values or {}
    names = _unique_preserving_order(secret_names)
    header = [
        (
            f"# Secret references for {display_name}"
            if display_name
            else "# Secret references"
        ),
        "# Keys declared here are synthesized into runtime.secret_refs for the bot.",
    ]
    lines = list(header)
    for name in names:
        lines.append("")
        lines.append(f"{name}={values.get(name, '')}")
    return "\n".join(lines).rstrip() + "\n"


def write_secret_env(
    path: str | Path,
    secret_names: list[str],
    *,
    existing_values: dict[str, str] | None = None,
    display_name: str | None = None,
) -> None:
    """Write the canonical bot .env file."""
    Path(path).write_text(
        render_secret_env(
            secret_names,
            existing_values=existing_values,
            display_name=display_name,
        ),
        encoding="utf-8",
    )


def parse_secret_env_text(text: str, *, label: str) -> list[tuple[str, str]]:
    """Parse a bot sidecar .env file."""
    entries: list[tuple[str, str]] = []
    seen: set[str] = set()
    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in raw_line:
            raise ValidationError(f"{label}:{line_no} must use KEY=VALUE syntax.")
        name, value = raw_line.split("=", 1)
        name = name.strip()
        if not _ENV_KEY_PATTERN.match(name):
            raise ValidationError(
                f"{label}:{line_no} has an invalid env var name: {name!r}"
            )
        if name in seen:
            raise ValidationError(f"{label}:{line_no} duplicates env var {name}.")
        seen.add(name)
        entries.append((name, value))
    return entries


def _unique_preserving_order(items: list[str]) -> list[str]:
    """Remove duplicates from secret names while preserving the first declared order."""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
