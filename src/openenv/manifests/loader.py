"""Manifest parsing and validation."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path, PurePosixPath
from typing import Any

from openenv.core.errors import ValidationError
from openenv.core.models import (
    AccessConfig,
    AgentConfig,
    Manifest,
    OpenClawConfig,
    ProjectConfig,
    RuntimeConfig,
    SandboxConfig,
    SecretRef,
    SkillConfig,
)
from openenv.core.skills import ensure_mandatory_skills
from openenv.envfiles.secret_env import load_secret_refs

_SENSITIVE_KEY_PATTERN = re.compile(
    r"(secret|token|password|api[_-]?key|access[_-]?key)", re.IGNORECASE
)


def load_manifest(path: str | Path) -> tuple[Manifest, str]:
    """Read and parse a manifest from disk."""
    manifest_path = Path(path)
    try:
        raw_text = manifest_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ValidationError(f"Manifest file not found: {manifest_path}") from exc
    try:
        data = tomllib.loads(raw_text)
    except tomllib.TOMLDecodeError as exc:
        raise ValidationError(f"Invalid TOML in {manifest_path}: {exc}") from exc
    manifest = parse_manifest(data, base_dir=manifest_path.parent)
    sidecar_secret_refs = load_secret_refs(manifest_path.parent / ".env")
    if sidecar_secret_refs:
        if manifest.runtime.secret_refs:
            raise ValidationError(
                "Declare secret refs either in runtime.secret_refs or in a sibling .env file, not both."
            )
        manifest.runtime.secret_refs = sidecar_secret_refs
    return manifest, raw_text


def parse_manifest(
    data: dict[str, Any],
    *,
    base_dir: Path | None = None,
) -> Manifest:
    """Convert parsed TOML into a strongly typed manifest."""
    if not isinstance(data, dict):
        raise ValidationError("Manifest root must be a TOML table.")

    schema_version = data.get("schema_version")
    if schema_version != 1:
        raise ValidationError("schema_version must be set to 1.")

    project_table = _require_table(data, "project")
    runtime_table = _require_table(data, "runtime")
    agent_table = _require_table(data, "agent")
    openclaw_table = _require_table(data, "openclaw")
    access_table = data.get("access", {})
    if access_table and not isinstance(access_table, dict):
        raise ValidationError("access must be a table when provided.")

    project = ProjectConfig(
        name=_require_string(project_table, "name"),
        version=_require_string(project_table, "version"),
        description=_require_string(project_table, "description"),
        runtime=_require_string(project_table, "runtime"),
    )
    if project.runtime != "openclaw":
        raise ValidationError("project.runtime must currently be 'openclaw'.")

    runtime = RuntimeConfig(
        base_image=_require_string(runtime_table, "base_image"),
        python_version=_require_string(runtime_table, "python_version"),
        system_packages=_string_list(
            runtime_table.get("system_packages", []),
            "runtime.system_packages",
        ),
        python_packages=_string_list(
            runtime_table.get("python_packages", []),
            "runtime.python_packages",
        ),
        node_packages=_string_list(
            runtime_table.get("node_packages", []),
            "runtime.node_packages",
        ),
        env=_string_map(runtime_table.get("env", {}), "runtime.env"),
        user=_optional_string(runtime_table.get("user"), "runtime.user") or "root",
        workdir=_optional_string(runtime_table.get("workdir"), "runtime.workdir")
        or "/workspace",
        secret_refs=_parse_secret_refs(runtime_table.get("secret_refs", [])),
    )
    _validate_runtime(runtime)

    agent = _parse_agent_config(agent_table, base_dir=base_dir)

    skills_raw = data.get("skills", [])
    if not isinstance(skills_raw, list):
        raise ValidationError("skills must be an array of tables.")
    skills = [_parse_skill(item, index) for index, item in enumerate(skills_raw, start=1)]
    skills = ensure_mandatory_skills(skills)
    _validate_skill_names(skills)

    sandbox_table = _require_table(openclaw_table, "sandbox")
    tools_table = openclaw_table.get("tools", {})
    if not isinstance(tools_table, dict):
        raise ValidationError("openclaw.tools must be a table when provided.")

    openclaw = OpenClawConfig(
        agent_id=_require_string(openclaw_table, "agent_id"),
        agent_name=_require_string(openclaw_table, "agent_name"),
        workspace=_optional_string(openclaw_table.get("workspace"), "openclaw.workspace")
        or "/opt/openclaw/workspace",
        state_dir=_optional_string(openclaw_table.get("state_dir"), "openclaw.state_dir")
        or "/opt/openclaw",
        tools_allow=_string_list(tools_table.get("allow", []), "openclaw.tools.allow"),
        tools_deny=_string_list(tools_table.get("deny", []), "openclaw.tools.deny"),
        sandbox=SandboxConfig(
            mode=_require_string(sandbox_table, "mode"),
            scope=_require_string(sandbox_table, "scope"),
            workspace_access=_require_string(sandbox_table, "workspace_access"),
            network=_require_string(sandbox_table, "network"),
            read_only_root=_require_bool(sandbox_table, "read_only_root"),
        ),
    )
    _validate_openclaw(openclaw)

    access = AccessConfig(
        websites=_string_list(access_table.get("websites", []), "access.websites"),
        databases=_string_list(access_table.get("databases", []), "access.databases"),
        notes=_string_list(access_table.get("notes", []), "access.notes"),
    )

    return Manifest(
        schema_version=schema_version,
        project=project,
        runtime=runtime,
        agent=agent,
        skills=skills,
        openclaw=openclaw,
        access=access,
    )


def _parse_secret_refs(value: Any) -> list[SecretRef]:
    """Parse inline `runtime.secret_refs` entries into typed secret references."""
    if not isinstance(value, list):
        raise ValidationError("runtime.secret_refs must be an array of tables.")
    secret_refs: list[SecretRef] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            raise ValidationError(f"runtime.secret_refs[{index}] must be a table.")
        secret_refs.append(
            SecretRef(
                name=_require_string(item, "name", prefix=f"runtime.secret_refs[{index}]"),
                source=_require_string(item, "source", prefix=f"runtime.secret_refs[{index}]"),
                required=(
                    _optional_bool(
                        item.get("required"),
                        f"runtime.secret_refs[{index}].required",
                    )
                    if "required" in item
                    else True
                ),
            )
        )
    return secret_refs


def _parse_agent_config(
    agent_table: dict[str, Any],
    *,
    base_dir: Path | None = None,
) -> AgentConfig:
    """Parse the `[agent]` table, resolving optional markdown file references."""
    agents_md, agents_md_ref = _parse_agent_document(
        agent_table,
        "agents_md",
        base_dir=base_dir,
    )
    soul_md, soul_md_ref = _parse_agent_document(
        agent_table,
        "soul_md",
        base_dir=base_dir,
    )
    user_md, user_md_ref = _parse_agent_document(
        agent_table,
        "user_md",
        base_dir=base_dir,
    )
    identity_md, identity_md_ref = _parse_agent_document(
        agent_table,
        "identity_md",
        base_dir=base_dir,
        required=False,
    )
    tools_md, tools_md_ref = _parse_agent_document(
        agent_table,
        "tools_md",
        base_dir=base_dir,
        required=False,
    )
    memory_seed, memory_seed_ref = _parse_memory_seed(
        agent_table.get("memory_seed", []),
        base_dir=base_dir,
    )
    return AgentConfig(
        agents_md=agents_md,
        soul_md=soul_md,
        user_md=user_md,
        identity_md=identity_md,
        tools_md=tools_md,
        memory_seed=memory_seed,
        agents_md_ref=agents_md_ref,
        soul_md_ref=soul_md_ref,
        user_md_ref=user_md_ref,
        identity_md_ref=identity_md_ref,
        tools_md_ref=tools_md_ref,
        memory_seed_ref=memory_seed_ref,
    )


def _parse_memory_seed(
    value: Any,
    *,
    base_dir: Path | None = None,
) -> tuple[list[str], str | None]:
    """Parse `agent.memory_seed` from inline text, a list, or a referenced markdown file."""
    if isinstance(value, str):
        if base_dir is not None and _looks_like_markdown_ref(value):
            memory_ref = _validate_markdown_ref(value, "agent.memory_seed")
            content = _read_markdown_ref(base_dir, memory_ref, "agent.memory_seed")
            return _split_memory_seed(content), memory_ref
        return _split_memory_seed(value), None
    return _string_list(value, "agent.memory_seed"), None


def _parse_agent_document(
    agent_table: dict[str, Any],
    key: str,
    *,
    base_dir: Path | None = None,
    required: bool = True,
) -> tuple[str | None, str | None]:
    """Parse one agent markdown field and optionally dereference a sibling `.md` file."""
    label = f"agent.{key}"
    if key not in agent_table:
        if required:
            raise ValidationError(f"{label} must be a non-empty string.")
        return None, None

    value = _optional_string(agent_table.get(key), label)
    if value is None:
        return None, None
    if base_dir is not None and _looks_like_markdown_ref(value):
        ref = _validate_markdown_ref(value, label)
        return _read_markdown_ref(base_dir, ref, label), ref
    return value, None


def _split_memory_seed(value: str) -> list[str]:
    """Normalize multiline memory seed text into a list of non-empty logical lines."""
    return [line.rstrip() for line in value.splitlines() if line.strip()]


def _looks_like_markdown_ref(value: str) -> bool:
    """Return whether a manifest string should be interpreted as a markdown file path."""
    return "\n" not in value and value.strip().lower().endswith(".md")


def _validate_markdown_ref(value: str, label: str) -> str:
    """Ensure a markdown file reference stays inside the manifest directory."""
    normalized = PurePosixPath(value.replace("\\", "/"))
    if Path(value).is_absolute() or normalized.is_absolute() or ".." in normalized.parts:
        raise ValidationError(
            f"{label} reference must stay within the manifest directory: {value}"
        )
    return value


def _read_markdown_ref(base_dir: Path, relative_path: str, label: str) -> str:
    """Read and validate a referenced markdown file from disk."""
    file_path = base_dir / Path(relative_path)
    try:
        content = file_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ValidationError(
            f"{label} references a missing file: {relative_path}"
        ) from exc
    if not file_path.is_file():
        raise ValidationError(f"{label} reference must point to a file: {relative_path}")
    if not content.strip():
        raise ValidationError(f"{label} file cannot be empty: {relative_path}")
    return content


def _parse_skill(item: Any, index: int) -> SkillConfig:
    """Parse one `[[skills]]` entry, including optional inline assets and source refs."""
    if not isinstance(item, dict):
        raise ValidationError(f"skills[{index}] must be a table.")
    assets = _string_map(item.get("assets", {}), f"skills[{index}].assets")
    for asset_path in assets:
        normalized = PurePosixPath(asset_path)
        if normalized.is_absolute() or ".." in normalized.parts:
            raise ValidationError(
                f"skills[{index}].assets path must stay within the skill directory: {asset_path}"
            )
    skill = SkillConfig(
        name=_require_string(item, "name", prefix=f"skills[{index}]"),
        description=_require_string(item, "description", prefix=f"skills[{index}]"),
        content=_optional_string(item.get("content"), f"skills[{index}].content"),
        source=_optional_string(item.get("source"), f"skills[{index}].source"),
        assets=assets,
    )
    if skill.content is None and skill.source is None:
        raise ValidationError(
            f"skills[{index}] must define either content or source."
        )
    if skill.content is not None and not skill.content.lstrip().startswith("---"):
        raise ValidationError(
            f"skills[{index}].content must be a full SKILL.md document with frontmatter."
        )
    return skill


def _validate_runtime(runtime: RuntimeConfig) -> None:
    """Validate runtime invariants that cannot be expressed by TOML typing alone."""
    if not runtime.base_image:
        raise ValidationError("runtime.base_image cannot be empty.")
    if not PurePosixPath(runtime.workdir).is_absolute():
        raise ValidationError("runtime.workdir must be an absolute POSIX path.")
    for key, value in runtime.env.items():
        if _SENSITIVE_KEY_PATTERN.search(key):
            raise ValidationError(
                "Sensitive environment variables must be declared via "
                "runtime.secret_refs, not runtime.env."
            )
        if not value:
            raise ValidationError(f"runtime.env.{key} cannot be empty.")


def _validate_openclaw(config: OpenClawConfig) -> None:
    """Validate OpenClaw-specific path invariants after parsing defaults."""
    if not PurePosixPath(config.workspace).is_absolute():
        raise ValidationError("openclaw.workspace must be an absolute POSIX path.")
    if not PurePosixPath(config.state_dir).is_absolute():
        raise ValidationError("openclaw.state_dir must be an absolute POSIX path.")
    allow_set = set(config.tools_allow)
    deny_set = set(config.tools_deny)
    overlapping = sorted(allow_set & deny_set)
    if overlapping:
        raise ValidationError(
            "openclaw.tools.allow and openclaw.tools.deny cannot overlap: "
            + ", ".join(overlapping)
        )


def _validate_skill_names(skills: list[SkillConfig]) -> None:
    """Reject duplicate skill names so workspace paths remain unique."""
    seen: set[str] = set()
    for skill in skills:
        if skill.name in seen:
            raise ValidationError(f"Duplicate skill name: {skill.name}")
        seen.add(skill.name)


def _require_table(
    data: dict[str, Any],
    key: str,
    *,
    prefix: str | None = None,
) -> dict[str, Any]:
    """Require a nested TOML table and raise a labeled validation error when missing."""
    value = data.get(key)
    if not isinstance(value, dict):
        label = f"{prefix}.{key}" if prefix else key
        raise ValidationError(f"{label} must be a table.")
    return value


def _require_string(
    data: dict[str, Any],
    key: str,
    *,
    prefix: str | None = None,
) -> str:
    """Require a non-empty string field from a parsed TOML table."""
    label = f"{prefix}.{key}" if prefix else key
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{label} must be a non-empty string.")
    return value


def _optional_string(value: Any, label: str) -> str | None:
    """Validate an optional string field, returning `None` when it is absent."""
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{label} must be a non-empty string when provided.")
    return value


def _require_bool(data: dict[str, Any], key: str, *, prefix: str | None = None) -> bool:
    """Require a boolean field from a parsed TOML table."""
    label = f"{prefix}.{key}" if prefix else key
    value = data.get(key)
    if not isinstance(value, bool):
        raise ValidationError(f"{label} must be a boolean.")
    return value


def _optional_bool(value: Any, label: str) -> bool:
    """Validate an optional boolean field that is present in the source payload."""
    if not isinstance(value, bool):
        raise ValidationError(f"{label} must be a boolean.")
    return value


def _string_list(value: Any, label: str) -> list[str]:
    """Validate that a manifest field is a list of non-empty strings."""
    if not isinstance(value, list):
        raise ValidationError(f"{label} must be a list of strings.")
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise ValidationError(f"{label} must contain only non-empty strings.")
    return list(value)


def _string_map(value: Any, label: str) -> dict[str, str]:
    """Validate that a manifest field is a table whose keys and values are strings."""
    if not isinstance(value, dict):
        raise ValidationError(f"{label} must be a table of string values.")
    result: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip():
            raise ValidationError(f"{label} keys must be non-empty strings.")
        if not isinstance(item, str):
            raise ValidationError(f"{label}.{key} must be a string.")
        result[key] = item
    return result
