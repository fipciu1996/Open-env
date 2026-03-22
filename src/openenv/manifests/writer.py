"""Manifest serialization helpers."""

from __future__ import annotations

import json

from openenv.core.models import Manifest


def render_manifest(manifest: Manifest) -> str:
    """Serialize a manifest dataclass into TOML."""
    lines: list[str] = [f"schema_version = {manifest.schema_version}", ""]

    lines.extend(["[project]"])
    lines.extend(_render_kv("name", manifest.project.name))
    lines.extend(_render_kv("version", manifest.project.version))
    lines.extend(_render_kv("description", manifest.project.description))
    lines.extend(_render_kv("runtime", manifest.project.runtime))
    lines.append("")

    lines.extend(["[runtime]"])
    lines.extend(_render_kv("base_image", manifest.runtime.base_image))
    lines.extend(_render_kv("python_version", manifest.runtime.python_version))
    lines.extend(_render_kv("system_packages", manifest.runtime.system_packages))
    lines.extend(_render_kv("python_packages", manifest.runtime.python_packages))
    lines.extend(_render_kv("node_packages", manifest.runtime.node_packages))
    if manifest.runtime.env:
        lines.append(f"env = {_render_inline_table(manifest.runtime.env)}")
    lines.extend(_render_kv("user", manifest.runtime.user))
    lines.extend(_render_kv("workdir", manifest.runtime.workdir))
    lines.append("")
    for secret in manifest.runtime.secret_refs:
        lines.extend(["[[runtime.secret_refs]]"])
        lines.extend(_render_kv("name", secret.name))
        lines.extend(_render_kv("source", secret.source))
        lines.extend(_render_kv("required", secret.required))
    lines.append("")

    lines.extend(["[agent]"])
    lines.extend(
        _render_agent_doc(
            "agents_md",
            manifest.agent.agents_md_ref,
            manifest.agent.agents_md,
        )
    )
    lines.extend(
        _render_agent_doc(
            "soul_md",
            manifest.agent.soul_md_ref,
            manifest.agent.soul_md,
        )
    )
    lines.extend(
        _render_agent_doc(
            "user_md",
            manifest.agent.user_md_ref,
            manifest.agent.user_md,
        )
    )
    if manifest.agent.identity_md is not None:
        lines.extend(
            _render_agent_doc(
                "identity_md",
                manifest.agent.identity_md_ref,
                manifest.agent.identity_md,
            )
        )
    if manifest.agent.tools_md is not None:
        lines.extend(
            _render_agent_doc(
                "tools_md",
                manifest.agent.tools_md_ref,
                manifest.agent.tools_md,
            )
        )
    if manifest.agent.memory_seed_ref is not None:
        lines.extend(_render_kv("memory_seed", manifest.agent.memory_seed_ref))
    else:
        lines.extend(_render_kv("memory_seed", manifest.agent.memory_seed))
    lines.append("")

    for skill in manifest.skills:
        lines.extend(["[[skills]]"])
        lines.extend(_render_kv("name", skill.name))
        lines.extend(_render_kv("description", skill.description))
        if skill.source is not None:
            lines.extend(_render_kv("source", skill.source))
        if skill.content is not None:
            lines.extend(_render_kv("content", skill.content))
        if skill.assets:
            lines.append(f"assets = {_render_inline_table(skill.assets)}")
        lines.append("")

    if manifest.access.websites or manifest.access.databases or manifest.access.notes:
        lines.extend(["[access]"])
        lines.extend(_render_kv("websites", manifest.access.websites))
        lines.extend(_render_kv("databases", manifest.access.databases))
        lines.extend(_render_kv("notes", manifest.access.notes))
        lines.append("")

    lines.extend(["[openclaw]"])
    lines.extend(_render_kv("agent_id", manifest.openclaw.agent_id))
    lines.extend(_render_kv("agent_name", manifest.openclaw.agent_name))
    lines.extend(_render_kv("workspace", manifest.openclaw.workspace))
    lines.extend(_render_kv("state_dir", manifest.openclaw.state_dir))
    lines.append("")

    lines.extend(["[openclaw.sandbox]"])
    lines.extend(_render_kv("mode", manifest.openclaw.sandbox.mode))
    lines.extend(_render_kv("scope", manifest.openclaw.sandbox.scope))
    lines.extend(_render_kv("workspace_access", manifest.openclaw.sandbox.workspace_access))
    lines.extend(_render_kv("network", manifest.openclaw.sandbox.network))
    lines.extend(_render_kv("read_only_root", manifest.openclaw.sandbox.read_only_root))
    lines.append("")

    lines.extend(["[openclaw.tools]"])
    lines.extend(_render_kv("allow", manifest.openclaw.tools_allow))
    lines.extend(_render_kv("deny", manifest.openclaw.tools_deny))
    lines.append("")
    return "\n".join(lines)


def _render_agent_doc(key: str, reference: str | None, content: str) -> list[str]:
    """Serialize one agent markdown field, preferring a file reference when available."""
    if reference is not None:
        return _render_kv(key, reference)
    return _render_kv(key, content)


def _render_kv(key: str, value: object) -> list[str]:
    """Render a single TOML key/value pair, including multiline string blocks."""
    if isinstance(value, str):
        if "\n" in value:
            rendered = value.rstrip("\n")
            return [f'{key} = """', rendered, '"""']
        return [f"{key} = {json.dumps(value)}"]
    if isinstance(value, bool):
        return [f"{key} = {'true' if value else 'false'}"]
    if isinstance(value, list):
        if not value:
            return [f"{key} = []"]
        rendered_items = ", ".join(json.dumps(item) for item in value)
        return [f"{key} = [{rendered_items}]"]
    raise TypeError(f"Unsupported TOML value for {key}: {type(value)!r}")


def _render_inline_table(values: dict[str, str]) -> str:
    """Render a deterministic inline TOML table with JSON-style string escaping."""
    rendered = ", ".join(
        f"{json.dumps(key)} = {json.dumps(value)}" for key, value in sorted(values.items())
    )
    return "{ " + rendered + " }"
