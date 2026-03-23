# Security Notes

## Secure By Default, Not Operator-Hostile

OpenClaw-env-manager is designed to start from a hardened baseline without
silently overriding explicit operator intent.

That means:

- newly generated manifests and Docker/Compose artifacts use safer defaults
- risky explicit choices are still possible when they are really needed
- validation, export, and build flows surface those choices as non-blocking
  security advisories

The goal is to keep the operator in control while making risk visible and
harder to miss.

## Default Security Mechanisms

OpenClaw-env-manager currently applies or generates these default protections:

- `read_only_root = true` in generated OpenClaw sandbox configuration
- localhost-only binds for generated gateway and bridge ports
- `cap_drop: [ALL]` for generated Compose services
- `security_opt: ["no-new-privileges:true"]`
- read-only container root filesystems in generated Compose services
- constrained writable scratch space through `tmpfs`
- process and file descriptor limits through `pids_limit` and `ulimits`
- separation of secrets into sidecar `.env` files instead of embedding them in
  the image
- build-time and preflight skill scanning with `cisco-ai-skill-scanner`
- mandatory baseline skills for context, self-improvement, and security review

## Default Skills And Tools Added To Generated Images

The secure baseline also includes a small set of default skills and tools that
are always materialized or installed in generated bot images unless the project
changes that baseline in code.

Mandatory skills currently normalized into the effective skill set:

- `deus-context-engine`
- `self-improving-agent`
- `skill-security-review`
- `freeride` (installed into the OpenClaw workspace as `free-ride`)
- `agent-browser-clawdbot`

Default tooling currently prepared inside the generated image:

- `chromium`
- `node`, `npm`, and `npx`
- global `agent-browser`, followed by `agent-browser install`
- `cisco-ai-skill-scanner`
- Python runtime packages from the manifest, installed into an image-local
  virtual environment
- Node.js packages from the manifest, installed globally
- `freeride` installed from ClawHub and exposed through the OpenClaw workspace

This baseline is meant to make the image immediately usable for OpenClaw agent
execution, browser-assisted tasks, and security scanning. It does not prevent
the operator from adding further dependencies through `openclawenv.toml`.

## What Triggers Security Advisories

OpenClaw-env-manager warns when a manifest or runtime override weakens the
default posture. Current advisory examples include:

- `runtime.base_image` not pinned with `@sha256`
- `runtime.user = "root"`
- `openclaw.sandbox.read_only_root = false`
- sandbox network access broader than `none`
- wildcard tool policies such as `*` or `all`
- explicit `shell_command` allowlists
- public host binds such as `OPENCLAW_GATEWAY_HOST_BIND=0.0.0.0`
- `OPENCLAW_ALLOW_INSECURE_PRIVATE_WS` enabled

These are warnings rather than hard failures, because the operator may have a
valid reason to make that trade-off.

## What Is Still Intentionally Enforced

Some cases remain hard validation errors because they indicate an inconsistent
or unsafe configuration shape rather than an explicit trade-off. For example:

- malformed manifests
- overlapping `openclaw.tools.allow` and `openclaw.tools.deny`
- invalid secret declarations
- path traversal in skill assets or markdown references

## Security Responsibilities Outside The Tool

OpenClaw-env-manager can improve defaults and warn about risk, but it cannot
replace platform-level hardening. You still need to manage:

- Docker daemon exposure and `docker.sock` mounts
- host firewall rules and port exposure
- rootless Docker or user namespace isolation
- seccomp, AppArmor, or SELinux policy on the host
- kernel, Docker, and OS patching
- secret storage and rotation outside local bot sidecars

## Reference Baseline

The default posture and guidance in this project intentionally align with the
[OWASP Cheat Sheet Series](https://github.com/OWASP/CheatSheetSeries),
especially:

- [Docker Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html)
- [AI Agent Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/AI_Agent_Security_Cheat_Sheet.html)

## Related Pages

- [Getting Started](getting-started.md)
- [Concepts](concepts.md)
- [`openclawenv.toml` Structure](openclawenv-toml.md)
