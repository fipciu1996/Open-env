# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project aims to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-03-22

### Added

- Initial `Open-env` release with declarative `openenv.toml` manifests and
  deterministic `openenv.lock` generation for OpenClaw agent environments.
- CLI workflows for `init`, `validate`, `lock`, `export dockerfile`,
  `export compose`, `build`, and local skill scanning.
- Generated Docker and OpenClaw Compose artifacts with support for Python,
  Node.js, Chromium, `agent-browser`, `freeride`, and build-time skill
  scanning with `cisco-ai-skill-scanner`.
- Interactive multilingual bot management for listing, creating, editing,
  deleting, exporting, and inspecting bots and their running containers.
- Bot-specific secret handling through sidecar `.env` files and markdown-based
  agent document management with file references stored in manifests.
- OpenRouter-powered markdown improvement flow with batched processing to
  reduce token cost and normalize generated bot documents to English.
- Snapshot support for running bots that inspects installed skills in
  containers and merges discovered changes back into bot manifests.
- CI, coverage reporting, MkDocs plus `mkdocstrings` documentation, GitLab
  Pages publishing, and a tag-only GitHub Actions workflow for publishing the
  package to PyPI.
