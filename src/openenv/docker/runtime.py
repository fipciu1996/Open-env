"""Runtime inspection helpers for running bot containers."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field

from openenv.core.errors import CommandError


SNAPSHOT_SCRIPT_TEMPLATE = """\
import json
from pathlib import Path

skills_root = Path({workspace!r}) / "skills"
payload = []
if skills_root.exists():
    for skill_dir in sorted(path for path in skills_root.iterdir() if path.is_dir()):
        files = {{}}
        for file_path in sorted(path for path in skill_dir.rglob("*") if path.is_file()):
            relative_path = file_path.relative_to(skill_dir).as_posix()
            files[relative_path] = file_path.read_text(encoding="utf-8", errors="replace")
        payload.append({{"name": skill_dir.name, "files": files}})
print(json.dumps(payload, sort_keys=True))
"""


@dataclass(slots=True)
class CapturedSkill:
    """A skill snapshot collected from a running container."""

    name: str
    description: str
    content: str
    source: str | None = None
    assets: dict[str, str] = field(default_factory=dict)


def list_running_container_names() -> set[str]:
    """Return the names of running Docker containers."""
    stdout = _run_command(
        ["docker", "ps", "--format", "{{.Names}}"],
        unavailable_message=(
            "Docker is not available on PATH. Install Docker or Docker Desktop "
            "before listing running bots."
        ),
        failure_message="Failed to list running Docker containers.",
    )
    return {line.strip() for line in stdout.splitlines() if line.strip()}


def fetch_container_logs(container_name: str, *, tail: int = 120) -> str:
    """Return recent logs for a running container."""
    return _run_command(
        ["docker", "logs", "--tail", str(tail), container_name],
        unavailable_message=(
            "Docker is not available on PATH. Install Docker or Docker Desktop "
            "before reading bot logs."
        ),
        failure_message=f"Failed to read logs for container `{container_name}`.",
    )


def snapshot_installed_skills(
    container_name: str,
    *,
    workspace: str,
) -> list[CapturedSkill]:
    """Snapshot installed skills from a running bot container."""
    stdout = _run_command(
        [
            "docker",
            "exec",
            container_name,
            "python",
            "-c",
            SNAPSHOT_SCRIPT_TEMPLATE.format(workspace=workspace),
        ],
        unavailable_message=(
            "Docker is not available on PATH. Install Docker or Docker Desktop "
            "before creating a skill snapshot."
        ),
        failure_message=f"Failed to snapshot installed skills for `{container_name}`.",
    )
    try:
        payload = json.loads(stdout.strip() or "[]")
    except json.JSONDecodeError as exc:
        raise CommandError(
            f"Container `{container_name}` returned an unreadable skill snapshot payload."
        ) from exc
    if not isinstance(payload, list):
        raise CommandError(
            f"Container `{container_name}` returned an invalid skill snapshot payload."
        )

    snapshots: list[CapturedSkill] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        files = item.get("files", {})
        if not name or not isinstance(files, dict):
            continue
        skill_md = files.get("SKILL.md")
        if not isinstance(skill_md, str) or not skill_md.strip():
            continue
        assets = {
            path: content
            for path, content in sorted(files.items())
            if path != "SKILL.md" and isinstance(path, str) and isinstance(content, str)
        }
        frontmatter = _parse_frontmatter(skill_md)
        snapshots.append(
            CapturedSkill(
                name=name,
                description=frontmatter.get(
                    "description",
                    f"Snapshotted skill from running container {container_name}",
                ),
                content=skill_md,
                source=frontmatter.get("source"),
                assets=assets,
            )
        )
    return snapshots


def _run_command(
    command: list[str],
    *,
    unavailable_message: str,
    failure_message: str,
) -> str:
    """Execute a Docker command and normalize transport and process failures."""
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise CommandError(unavailable_message) from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        details = f" Docker said: {stderr}" if stderr else ""
        raise CommandError(f"{failure_message}{details}", exit_code=exc.returncode) from exc
    return completed.stdout


def _parse_frontmatter(content: str) -> dict[str, str]:
    """Extract a simple YAML-frontmatter key/value mapping from `SKILL.md` content."""
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fields: dict[str, str] = {}
    for line in lines[1:]:
        stripped = line.strip()
        if stripped == "---":
            break
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip().lower()] = value.strip()
    return fields
