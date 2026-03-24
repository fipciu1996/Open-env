"""docker-compose generation for OpenClawenv."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import json
from pathlib import Path
import secrets

from pathlib import PurePosixPath

from openenv.core.models import Lockfile, Manifest
from openenv.core.security import assess_runtime_env_security
from openenv.core.utils import slugify_name
from openenv.docker.dockerfile import render_runtime_payload


OPENCLAW_GATEWAY_SERVICE = "openclaw-gateway"
OPENCLAW_CLI_SERVICE = "openclaw-cli"
OPENCLAW_CLI_ENTRYPOINT = ("node", "dist/index.js")
DEFAULT_OPENCLAW_HOME = "/home/node"
DEFAULT_OPENCLAW_CONFIG_DIR = "./.openclaw"
DEFAULT_OPENCLAW_WORKSPACE_DIR = "./workspace"
DEFAULT_OPENCLAW_GATEWAY_HOST_BIND = "127.0.0.1"
DEFAULT_OPENCLAW_BRIDGE_HOST_BIND = "127.0.0.1"
DEFAULT_OPENCLAW_GATEWAY_PORT = "18789"
DEFAULT_OPENCLAW_BRIDGE_PORT = "18790"
DEFAULT_OPENCLAW_GATEWAY_BIND = "lan"
DEFAULT_OPENCLAW_TIMEZONE = "UTC"
DEFAULT_OPENCLAW_TMPFS = "/tmp:rw,noexec,nosuid,nodev,size=64m"
DEFAULT_OPENCLAW_PIDS_LIMIT = "256"
DEFAULT_OPENCLAW_NOFILE_SOFT = "1024"
DEFAULT_OPENCLAW_NOFILE_HARD = "2048"
DEFAULT_OPENCLAW_NPROC = "512"
DEFAULT_BUILD_CONTEXT = "."
DEFAULT_DOCKERFILE_NAME = "Dockerfile"
DEFAULT_OPENCLAW_GATEWAY_IMAGE = "ghcr.io/openclaw/openclaw:latest"
LEGACY_OPENCLAW_IMAGE = "alpine/openclaw:main"
ALL_BOTS_GATEWAY_SERVICE = "openclaw-gateway"
ALL_BOTS_GATEWAY_CONTAINER = "all-bots-openclaw-gateway"
ALL_BOTS_COMPOSE_FILENAME = "all-bots-compose.yml"
ALL_BOTS_ENV_FILENAME = ".all-bots.env"
ALL_BOTS_GATEWAY_CONFIG_DIR = "./.all-bots/.openclaw"
ALL_BOTS_GATEWAY_WORKSPACE_DIR = "./.all-bots/workspace"
ALL_BOTS_GATEWAY_STATE_DIR = "/opt/openclaw"
ALL_BOTS_GATEWAY_CONFIG_PATH = f"{ALL_BOTS_GATEWAY_STATE_DIR}/openclaw.json"
DEFAULT_OPENCLAW_ENV_DEFAULTS: tuple[tuple[str, str], ...] = (
    ("OPENCLAW_GATEWAY_TOKEN", ""),
    ("OPENCLAW_ALLOW_INSECURE_PRIVATE_WS", ""),
    ("CLAUDE_AI_SESSION_KEY", ""),
    ("CLAUDE_WEB_SESSION_KEY", ""),
    ("CLAUDE_WEB_COOKIE", ""),
)


@dataclass(slots=True, frozen=True)
class AllBotsComposeSpec:
    """Information needed to render one bot entry inside the shared compose stack."""

    slug: str
    manifest: Manifest
    image_tag: str


def default_compose_filename(agent_name: str) -> str:
    """Return the default compose filename for a bot."""
    return f"docker-compose-{slugify_name(agent_name)}.yml"


def default_env_filename(agent_name: str) -> str:
    """Return the default env filename for a bot."""
    return f".{slugify_name(agent_name)}.env"


def all_bots_compose_filename() -> str:
    """Return the shared compose filename for all managed bots."""
    return ALL_BOTS_COMPOSE_FILENAME


def all_bots_env_filename() -> str:
    """Return the shared env filename used by the all-bots stack."""
    return ALL_BOTS_ENV_FILENAME


def gateway_container_name(agent_name: str) -> str:
    """Return the gateway container name for a bot."""
    return f"{slugify_name(agent_name)}-openclaw-gateway"


def cli_container_name(agent_name: str) -> str:
    """Return the CLI container name for a bot."""
    return f"{slugify_name(agent_name)}-openclaw-cli"


def render_compose(manifest: Manifest, image_tag: str) -> str:
    """Render an OpenClaw-style docker-compose file for the bot image."""
    env_file = default_env_filename(manifest.openclaw.agent_name)
    gateway_name = gateway_container_name(manifest.openclaw.agent_name)
    cli_name = cli_container_name(manifest.openclaw.agent_name)
    image_ref = f"${{OPENCLAW_IMAGE:-{image_tag}}}"
    config_mount = (
        f"${{OPENCLAW_CONFIG_DIR:-{DEFAULT_OPENCLAW_CONFIG_DIR}}}:{manifest.openclaw.state_dir}"
    )
    workspace_mount = (
        f"${{OPENCLAW_WORKSPACE_DIR:-{DEFAULT_OPENCLAW_WORKSPACE_DIR}}}:"
        f"{manifest.openclaw.workspace}"
    )
    gateway_env = _base_service_environment(manifest)
    cli_env = dict(gateway_env)
    cli_env["BROWSER"] = "echo"

    lines = [
        "services:",
        f"  {OPENCLAW_GATEWAY_SERVICE}:",
        f"    image: {_quoted(image_ref)}",
        "    build:",
        f"      context: {_quoted(DEFAULT_BUILD_CONTEXT)}",
        f"      dockerfile: {_quoted(DEFAULT_DOCKERFILE_NAME)}",
        "      args:",
        '        OPENCLAW_INSTALL_BROWSER: "${OPENCLAW_INSTALL_BROWSER:-}"',
        '        OPENCLAW_INSTALL_DOCKER_CLI: "${OPENCLAW_INSTALL_DOCKER_CLI:-}"',
        f"    container_name: {_quoted(gateway_name)}",
        "    env_file:",
        f"      - {_quoted(env_file)}",
        "    environment:",
    ]
    lines.extend(_render_environment(gateway_env))
    lines.extend(
        [
            "    cap_drop:",
            "      - ALL",
            "    security_opt:",
            "      - no-new-privileges:true",
            "    read_only: true",
            "    tmpfs:",
            f'      - "${{OPENCLAW_TMPFS:-{DEFAULT_OPENCLAW_TMPFS}}}"',
            f'    pids_limit: "${{OPENCLAW_PIDS_LIMIT:-{DEFAULT_OPENCLAW_PIDS_LIMIT}}}"',
            "    ulimits:",
            "      nofile:",
            f'        soft: "${{OPENCLAW_NOFILE_SOFT:-{DEFAULT_OPENCLAW_NOFILE_SOFT}}}"',
            f'        hard: "${{OPENCLAW_NOFILE_HARD:-{DEFAULT_OPENCLAW_NOFILE_HARD}}}"',
            f'      nproc: "${{OPENCLAW_NPROC:-{DEFAULT_OPENCLAW_NPROC}}}"',
            "    volumes:",
            f"      - {_quoted(config_mount)}",
            f"      - {_quoted(workspace_mount)}",
            "      ## Uncomment the lines below to enable sandbox isolation",
            "      ## (agents.defaults.sandbox). Requires Docker CLI in the image",
            "      ## (build with --build-arg OPENCLAW_INSTALL_DOCKER_CLI=1) or use",
            "      ## scripts/docker/setup.sh with OPENCLAW_SANDBOX=1 for automated setup.",
            "      ## WARNING: mounting /var/run/docker.sock grants host root-equivalent access.",
            "      ## Set DOCKER_GID to the host docker group GID before enabling it.",
            '      # - "/var/run/docker.sock:/var/run/docker.sock"',
            "    # group_add:",
            '    #   - "${DOCKER_GID:-999}"',
            "    ports:",
            (
                f'      - "${{OPENCLAW_GATEWAY_HOST_BIND:-{DEFAULT_OPENCLAW_GATEWAY_HOST_BIND}}}'
                f':${{OPENCLAW_GATEWAY_PORT:-{DEFAULT_OPENCLAW_GATEWAY_PORT}}}:18789"'
            ),
            (
                f'      - "${{OPENCLAW_BRIDGE_HOST_BIND:-{DEFAULT_OPENCLAW_BRIDGE_HOST_BIND}}}'
                f':${{OPENCLAW_BRIDGE_PORT:-{DEFAULT_OPENCLAW_BRIDGE_PORT}}}:18790"'
            ),
            "    init: true",
            "    restart: unless-stopped",
            "    command:",
            "      [",
            '        "node",',
            '        "dist/index.js",',
            '        "gateway",',
            '        "--bind",',
            f'        "${{OPENCLAW_GATEWAY_BIND:-{DEFAULT_OPENCLAW_GATEWAY_BIND}}}",',
            '        "--port",',
            '        "18789",',
            "      ]",
            "    healthcheck:",
            "      test:",
            "        [",
            '          "CMD",',
            '          "node",',
            '          "-e",',
            '          "fetch(\'http://127.0.0.1:18789/healthz\').then((r)=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))",',
            "        ]",
            "      interval: 30s",
            "      timeout: 5s",
            "      retries: 5",
            "      start_period: 20s",
            "",
            f"  {OPENCLAW_CLI_SERVICE}:",
            f"    image: {_quoted(image_ref)}",
            f"    container_name: {_quoted(cli_name)}",
            '    network_mode: "service:openclaw-gateway"',
            "    cap_drop:",
            "      - ALL",
            "    security_opt:",
            "      - no-new-privileges:true",
            "    read_only: true",
            "    tmpfs:",
            f'      - "${{OPENCLAW_TMPFS:-{DEFAULT_OPENCLAW_TMPFS}}}"',
            f'    pids_limit: "${{OPENCLAW_PIDS_LIMIT:-{DEFAULT_OPENCLAW_PIDS_LIMIT}}}"',
            "    ulimits:",
            "      nofile:",
            f'        soft: "${{OPENCLAW_NOFILE_SOFT:-{DEFAULT_OPENCLAW_NOFILE_SOFT}}}"',
            f'        hard: "${{OPENCLAW_NOFILE_HARD:-{DEFAULT_OPENCLAW_NOFILE_HARD}}}"',
            f'      nproc: "${{OPENCLAW_NPROC:-{DEFAULT_OPENCLAW_NPROC}}}"',
            "    env_file:",
            f"      - {_quoted(env_file)}",
            "    environment:",
        ]
    )
    lines.extend(_render_environment(cli_env))
    lines.extend(
        [
            "    volumes:",
            f"      - {_quoted(config_mount)}",
            f"      - {_quoted(workspace_mount)}",
            "    stdin_open: true",
            "    tty: true",
            "    init: true",
            f"    entrypoint: [{', '.join(_quoted(part) for part in OPENCLAW_CLI_ENTRYPOINT)}]",
            "    depends_on:",
            f"      - {OPENCLAW_GATEWAY_SERVICE}",
        ]
    )
    return "\n".join(lines) + "\n"


def render_all_bots_compose(specs: Sequence[AllBotsComposeSpec]) -> str:
    """Render a shared stack with one gateway and CLI services for all bots."""
    if not specs:
        raise ValueError("At least one bot is required to render the shared compose stack.")
    shared_env_file = f"./{all_bots_env_filename()}"
    lines = [
        "services:",
        f"  {ALL_BOTS_GATEWAY_SERVICE}:",
        f'    image: {_quoted(f"${{OPENCLAW_GATEWAY_IMAGE:-{DEFAULT_OPENCLAW_GATEWAY_IMAGE}}}")}',
        f"    container_name: {_quoted(ALL_BOTS_GATEWAY_CONTAINER)}",
        "    env_file:",
        f"      - {_quoted(shared_env_file)}",
        "    environment:",
    ]
    lines.extend(_render_environment(_shared_gateway_environment()))
    lines.extend(
        [
            "    cap_drop:",
            "      - ALL",
            "    security_opt:",
            "      - no-new-privileges:true",
            "    read_only: true",
            "    tmpfs:",
            f'      - "${{OPENCLAW_TMPFS:-{DEFAULT_OPENCLAW_TMPFS}}}"',
            f'    pids_limit: "${{OPENCLAW_PIDS_LIMIT:-{DEFAULT_OPENCLAW_PIDS_LIMIT}}}"',
            "    ulimits:",
            "      nofile:",
            f'        soft: "${{OPENCLAW_NOFILE_SOFT:-{DEFAULT_OPENCLAW_NOFILE_SOFT}}}"',
            f'        hard: "${{OPENCLAW_NOFILE_HARD:-{DEFAULT_OPENCLAW_NOFILE_HARD}}}"',
            f'      nproc: "${{OPENCLAW_NPROC:-{DEFAULT_OPENCLAW_NPROC}}}"',
            "    volumes:",
            (
                f'      - "{ALL_BOTS_GATEWAY_CONFIG_DIR}:'
                f'{ALL_BOTS_GATEWAY_STATE_DIR}"'
            ),
            (
                f'      - "{ALL_BOTS_GATEWAY_WORKSPACE_DIR}:'
                f'{ALL_BOTS_GATEWAY_STATE_DIR}/workspace"'
            ),
            "    ports:",
            (
                f'      - "${{OPENCLAW_GATEWAY_HOST_BIND:-{DEFAULT_OPENCLAW_GATEWAY_HOST_BIND}}}'
                f':${{OPENCLAW_GATEWAY_PORT:-{DEFAULT_OPENCLAW_GATEWAY_PORT}}}:18789"'
            ),
            (
                f'      - "${{OPENCLAW_BRIDGE_HOST_BIND:-{DEFAULT_OPENCLAW_BRIDGE_HOST_BIND}}}'
                f':${{OPENCLAW_BRIDGE_PORT:-{DEFAULT_OPENCLAW_BRIDGE_PORT}}}:18790"'
            ),
            "    init: true",
            "    restart: unless-stopped",
            "    command:",
            "      [",
            '        "node",',
            '        "dist/index.js",',
            '        "gateway",',
            '        "--bind",',
            f'        "${{OPENCLAW_GATEWAY_BIND:-{DEFAULT_OPENCLAW_GATEWAY_BIND}}}",',
            '        "--port",',
            '        "18789",',
            "      ]",
            "    healthcheck:",
            "      test:",
            "        [",
            '          "CMD",',
            '          "node",',
            '          "-e",',
            '          "fetch(\'http://127.0.0.1:18789/healthz\').then((r)=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))",',
            "        ]",
            "      interval: 30s",
            "      timeout: 5s",
            "      retries: 5",
            "      start_period: 20s",
        ]
    )
    for spec in specs:
        service_name = _all_bots_cli_service_name(spec.slug)
        container_name = _all_bots_cli_container_name(spec.slug)
        env_file = f"./{spec.slug}/{default_env_filename(spec.manifest.openclaw.agent_name)}"
        config_mount = f"{ALL_BOTS_GATEWAY_CONFIG_DIR}:{ALL_BOTS_GATEWAY_STATE_DIR}"
        workspace_mount = (
            f"{ALL_BOTS_GATEWAY_WORKSPACE_DIR}:{ALL_BOTS_GATEWAY_STATE_DIR}/workspace"
        )
        cli_env = dict(_base_service_environment(spec.manifest))
        cli_env["OPENCLAW_CONFIG_PATH"] = ALL_BOTS_GATEWAY_CONFIG_PATH
        cli_env["OPENCLAW_STATE_DIR"] = ALL_BOTS_GATEWAY_STATE_DIR
        cli_env["BROWSER"] = "echo"
        lines.extend(
            [
                "",
                f"  {service_name}:",
                f"    image: {_quoted(spec.image_tag)}",
                "    build:",
                f'      context: {_quoted(f"./{spec.slug}")}',
                f"      dockerfile: {_quoted(DEFAULT_DOCKERFILE_NAME)}",
                "      args:",
                '        OPENCLAW_INSTALL_BROWSER: "${OPENCLAW_INSTALL_BROWSER:-}"',
                '        OPENCLAW_INSTALL_DOCKER_CLI: "${OPENCLAW_INSTALL_DOCKER_CLI:-}"',
                f"    container_name: {_quoted(container_name)}",
                '    network_mode: "service:openclaw-gateway"',
                "    cap_drop:",
                "      - ALL",
                "    security_opt:",
                "      - no-new-privileges:true",
                "    read_only: true",
                "    tmpfs:",
                f'      - "${{OPENCLAW_TMPFS:-{DEFAULT_OPENCLAW_TMPFS}}}"',
                f'    pids_limit: "${{OPENCLAW_PIDS_LIMIT:-{DEFAULT_OPENCLAW_PIDS_LIMIT}}}"',
                "    ulimits:",
                "      nofile:",
                f'        soft: "${{OPENCLAW_NOFILE_SOFT:-{DEFAULT_OPENCLAW_NOFILE_SOFT}}}"',
                f'        hard: "${{OPENCLAW_NOFILE_HARD:-{DEFAULT_OPENCLAW_NOFILE_HARD}}}"',
                f'      nproc: "${{OPENCLAW_NPROC:-{DEFAULT_OPENCLAW_NPROC}}}"',
                "    env_file:",
                f"      - {_quoted(env_file)}",
                f"      - {_quoted(shared_env_file)}",
                "    environment:",
            ]
        )
        lines.extend(_render_environment(cli_env))
        lines.extend(
            [
                "    volumes:",
                f"      - {_quoted(config_mount)}",
                f"      - {_quoted(workspace_mount)}",
                "    stdin_open: true",
                "    tty: true",
                "    init: true",
                f"    entrypoint: [{', '.join(_quoted(part) for part in OPENCLAW_CLI_ENTRYPOINT)}]",
                "    depends_on:",
                f"      - {ALL_BOTS_GATEWAY_SERVICE}",
            ]
        )
    return "\n".join(lines) + "\n"


def write_compose(path: str | Path, compose_text: str) -> None:
    """Write the compose file to disk."""
    Path(path).write_text(compose_text, encoding="utf-8")


def render_env_file(
    manifest: Manifest,
    image_tag: str,
    *,
    existing_values: dict[str, str] | None = None,
) -> str:
    """Render the bot-specific env file with OpenClaw defaults and secrets."""
    values = dict(existing_values or {})
    secret_names = [secret.name for secret in manifest.runtime.secret_refs]
    used_keys: set[str] = set()
    lines = [
        f"# OpenClaw runtime and secrets for {manifest.openclaw.agent_name}",
        (
            "# Use with: docker compose --env-file "
            f"{default_env_filename(manifest.openclaw.agent_name)} -f "
            f"{default_compose_filename(manifest.openclaw.agent_name)} up -d"
        ),
        "",
        "# OpenClaw runtime overrides",
        "# docker compose builds and tags this image from the adjacent Dockerfile",
    ]
    runtime_defaults = {
        "OPENCLAW_IMAGE": image_tag,
        "OPENCLAW_CONFIG_DIR": DEFAULT_OPENCLAW_CONFIG_DIR,
        "OPENCLAW_WORKSPACE_DIR": DEFAULT_OPENCLAW_WORKSPACE_DIR,
        "OPENCLAW_GATEWAY_HOST_BIND": DEFAULT_OPENCLAW_GATEWAY_HOST_BIND,
        "OPENCLAW_BRIDGE_HOST_BIND": DEFAULT_OPENCLAW_BRIDGE_HOST_BIND,
        "OPENCLAW_GATEWAY_PORT": DEFAULT_OPENCLAW_GATEWAY_PORT,
        "OPENCLAW_BRIDGE_PORT": DEFAULT_OPENCLAW_BRIDGE_PORT,
        "OPENCLAW_GATEWAY_BIND": DEFAULT_OPENCLAW_GATEWAY_BIND,
        "OPENCLAW_STATE_DIR": manifest.openclaw.state_dir,
        "OPENCLAW_CONFIG_PATH": manifest.openclaw.config_path(),
        "OPENCLAW_TMPFS": DEFAULT_OPENCLAW_TMPFS,
        "OPENCLAW_PIDS_LIMIT": DEFAULT_OPENCLAW_PIDS_LIMIT,
        "OPENCLAW_NOFILE_SOFT": DEFAULT_OPENCLAW_NOFILE_SOFT,
        "OPENCLAW_NOFILE_HARD": DEFAULT_OPENCLAW_NOFILE_HARD,
        "OPENCLAW_NPROC": DEFAULT_OPENCLAW_NPROC,
        "OPENCLAW_TZ": DEFAULT_OPENCLAW_TIMEZONE,
        "OPENCLAW_INSTALL_BROWSER": "",
        "OPENCLAW_INSTALL_DOCKER_CLI": "",
    }
    for key, default in runtime_defaults.items():
        if key == "OPENCLAW_IMAGE":
            current_value = values.get(key)
            if current_value == LEGACY_OPENCLAW_IMAGE:
                value = default
            else:
                value = values.get(key, default)
        else:
            value = values.get(key, default)
        lines.append(f"{key}={value}")
        used_keys.add(key)
    for key, default in DEFAULT_OPENCLAW_ENV_DEFAULTS:
        lines.append(f"{key}={values.get(key, default)}")
        used_keys.add(key)
    advisory_values = {key: values.get(key, default) for key, default in runtime_defaults.items()}
    advisory_values.update(
        {key: values.get(key, default) for key, default in DEFAULT_OPENCLAW_ENV_DEFAULTS}
    )
    advisories = assess_runtime_env_security(advisory_values)
    if advisories:
        lines.append("")
        lines.append("# Security advisories for explicit runtime overrides")
        for advisory in advisories:
            lines.append(f"# WARNING: {advisory}")
    if secret_names:
        lines.append("")
        lines.append("# Bot secret references")
        for secret in manifest.runtime.secret_refs:
            lines.append("")
            lines.append(f"# source: {secret.source}")
            lines.append(f"# required: {'true' if secret.required else 'false'}")
            lines.append(f"{secret.name}={values.get(secret.name, '')}")
            used_keys.add(secret.name)
    extra_keys = sorted(key for key in values if key not in used_keys)
    if extra_keys:
        lines.append("")
        lines.append("# Preserved custom values")
        for key in extra_keys:
            lines.append(f"{key}={values[key]}")
    return "\n".join(lines).rstrip() + "\n"


def render_all_bots_env_file(*, existing_values: dict[str, str] | None = None) -> str:
    """Render the shared env file consumed by the all-bots gateway and CLI helpers."""
    values = dict(existing_values or {})
    lines = [
        "# Shared OpenClaw runtime secrets for the all-bots gateway",
        (
            "# Use with: docker compose -f "
            f"{all_bots_compose_filename()} up -d"
        ),
        "",
    ]
    for key, default in DEFAULT_OPENCLAW_ENV_DEFAULTS:
        lines.append(f"{key}={values.get(key, default)}")
    return "\n".join(lines).rstrip() + "\n"


def write_env_file(path: str | Path, env_text: str) -> None:
    """Write the env file to disk."""
    Path(path).write_text(env_text, encoding="utf-8")


def prepare_runtime_env_values(existing_values: dict[str, str] | None = None) -> dict[str, str]:
    """Fill runtime env values that should exist before writing generated env files."""
    values = dict(existing_values or {})
    if not values.get("OPENCLAW_GATEWAY_TOKEN", "").strip():
        values["OPENCLAW_GATEWAY_TOKEN"] = generate_gateway_token()
    return values


def generate_gateway_token() -> str:
    """Return a random gateway token for generated local stacks."""
    return secrets.token_urlsafe(24)


def _base_service_environment(manifest: Manifest) -> dict[str, str]:
    """Return environment variables shared by the gateway and CLI services for one bot."""
    environment = dict(sorted(manifest.runtime.env.items()))
    environment["HOME"] = DEFAULT_OPENCLAW_HOME
    environment["TERM"] = "xterm-256color"
    environment["OPENCLAW_CONFIG_PATH"] = manifest.openclaw.config_path()
    environment["OPENCLAW_STATE_DIR"] = manifest.openclaw.state_dir
    environment["TZ"] = f"${{OPENCLAW_TZ:-{DEFAULT_OPENCLAW_TIMEZONE}}}"
    return environment


def _shared_gateway_environment() -> dict[str, str]:
    """Return the baseline environment used by the shared gateway in the all-bots stack."""
    return {
        "HOME": DEFAULT_OPENCLAW_HOME,
        "TERM": "xterm-256color",
        "OPENCLAW_CONFIG_PATH": ALL_BOTS_GATEWAY_CONFIG_PATH,
        "OPENCLAW_STATE_DIR": ALL_BOTS_GATEWAY_STATE_DIR,
        "TZ": f"${{OPENCLAW_TZ:-{DEFAULT_OPENCLAW_TIMEZONE}}}",
    }


def _all_bots_cli_service_name(slug: str) -> str:
    """Build the service name used for one bot in the shared stack."""
    return f"bot-{slug}"


def _all_bots_cli_container_name(slug: str) -> str:
    """Build the container name used for one bot CLI in the shared stack."""
    return f"all-bots-{slug}-openclaw-cli"


def _render_environment(environment: dict[str, str]) -> list[str]:
    """Render compose `environment:` entries preserving the caller's ordering."""
    return [f"      {key}: {_quoted(value)}" for key, value in environment.items()]


def _quoted(value: str) -> str:
    """Return a YAML-safe quoted scalar using JSON string escaping."""
    return json.dumps(value)


def materialize_runtime_mount_tree(
    root: str | Path,
    manifest: Manifest,
    lockfile: Lockfile,
    *,
    raw_manifest_text: str,
    raw_lock_text: str,
) -> None:
    """Write the host-side runtime files expected by the generated bind mounts."""
    root_path = Path(root).resolve()
    state_root = root_path / DEFAULT_OPENCLAW_CONFIG_DIR.removeprefix("./")
    workspace_root = root_path / DEFAULT_OPENCLAW_WORKSPACE_DIR.removeprefix("./")
    payload = render_runtime_payload(
        manifest,
        lockfile,
        raw_manifest_text=raw_manifest_text,
        raw_lock_text=raw_lock_text,
    )
    directories = payload["directories"]
    files = payload["files"]
    if not isinstance(directories, list) or not isinstance(files, dict):
        raise TypeError("Runtime payload shape is invalid.")
    for directory in directories:
        host_path = _host_mount_path_for_container_path(
            str(directory),
            manifest,
            state_root=state_root,
            workspace_root=workspace_root,
        )
        if host_path is not None:
            host_path.mkdir(parents=True, exist_ok=True)
    agent_dir = _host_mount_path_for_container_path(
        manifest.openclaw.agent_dir(),
        manifest,
        state_root=state_root,
        workspace_root=workspace_root,
    )
    if agent_dir is not None:
        agent_dir.mkdir(parents=True, exist_ok=True)
    for container_path, content in sorted(files.items()):
        host_path = _host_mount_path_for_container_path(
            str(container_path),
            manifest,
            state_root=state_root,
            workspace_root=workspace_root,
        )
        if host_path is None or not isinstance(content, str):
            continue
        host_path.parent.mkdir(parents=True, exist_ok=True)
        host_path.write_text(content, encoding="utf-8")


def _host_mount_path_for_container_path(
    container_path: str,
    manifest: Manifest,
    *,
    state_root: Path,
    workspace_root: Path,
) -> Path | None:
    """Map one container path from the runtime payload to the exported host tree."""
    container = PurePosixPath(container_path)
    workspace = PurePosixPath(manifest.openclaw.workspace)
    state_dir = PurePosixPath(manifest.openclaw.state_dir)
    try:
        relative = container.relative_to(workspace)
    except ValueError:
        pass
    else:
        return _join_posix_relative(workspace_root, relative)
    try:
        relative = container.relative_to(state_dir)
    except ValueError:
        return None
    return _join_posix_relative(state_root, relative)


def _join_posix_relative(root: Path, relative: PurePosixPath) -> Path:
    """Join a POSIX-style relative path onto a host path."""
    if not relative.parts:
        return root
    return root.joinpath(*relative.parts)
