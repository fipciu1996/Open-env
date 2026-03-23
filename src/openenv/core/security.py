"""Security posture helpers for secure-by-default with explicit override support."""

from __future__ import annotations

from collections.abc import Mapping

from openenv.core.models import Manifest


_WILDCARD_TOOL_NAMES = {"*", "all"}
_LOOPBACK_BINDS = {"127.0.0.1", "localhost"}


def assess_manifest_security(manifest: Manifest) -> list[str]:
    """Return human-readable advisories for explicit manifest-level risk choices.

    The intent is to keep user overrides possible while making risky choices
    visible during validation, export, and build flows.
    """
    advisories: list[str] = []

    if "@sha256:" not in manifest.runtime.base_image:
        advisories.append(
            "runtime.base_image is not pinned with a digest; supply-chain trust and "
            "build reproducibility are reduced."
        )
    if manifest.runtime.user == "root":
        advisories.append(
            "runtime.user is set to root; containers should prefer an unprivileged "
            "runtime user when possible."
        )
    if not manifest.openclaw.sandbox.read_only_root:
        advisories.append(
            "openclaw.sandbox.read_only_root is disabled; writable roots increase the "
            "impact of agent or container compromise."
        )
    if manifest.openclaw.sandbox.network != "none":
        advisories.append(
            f"openclaw.sandbox.network={manifest.openclaw.sandbox.network!r}; outbound "
            "network access should be enabled only when the bot really needs it."
        )
    if any(
        tool_name.strip().lower() in _WILDCARD_TOOL_NAMES
        for tool_name in [*manifest.openclaw.tools_allow, *manifest.openclaw.tools_deny]
    ):
        advisories.append(
            "openclaw.tools contains wildcard entries; explicit tool names are safer "
            "and easier to audit."
        )
    if "shell_command" in manifest.openclaw.tools_allow:
        advisories.append(
            "openclaw.tools.allow includes shell_command; keep tool scopes narrow and "
            "use human approval for destructive actions."
        )
    return advisories


def assess_runtime_env_security(values: Mapping[str, str]) -> list[str]:
    """Return advisories for runtime env overrides that weaken deployment defaults."""
    advisories: list[str] = []

    gateway_bind = values.get("OPENCLAW_GATEWAY_HOST_BIND", "")
    if gateway_bind and gateway_bind not in _LOOPBACK_BINDS:
        advisories.append(
            "OPENCLAW_GATEWAY_HOST_BIND exposes the gateway beyond localhost; verify "
            "that external access is intentional and protected by host firewall rules."
        )

    bridge_bind = values.get("OPENCLAW_BRIDGE_HOST_BIND", "")
    if bridge_bind and bridge_bind not in _LOOPBACK_BINDS:
        advisories.append(
            "OPENCLAW_BRIDGE_HOST_BIND exposes the bridge beyond localhost; verify "
            "that external access is intentional and protected by host firewall rules."
        )

    if values.get("OPENCLAW_ALLOW_INSECURE_PRIVATE_WS", "").strip():
        advisories.append(
            "OPENCLAW_ALLOW_INSECURE_PRIVATE_WS is enabled; this weakens transport "
            "security for private websocket connections."
        )

    return advisories
