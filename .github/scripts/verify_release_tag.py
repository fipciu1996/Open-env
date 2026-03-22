"""Verify that the pushed Git tag matches the package version."""

from __future__ import annotations

import os
from pathlib import Path
import tomllib


def main() -> None:
    """Fail when the Git tag and the package version are out of sync."""
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    project_version = pyproject["project"]["version"]
    tag_name = os.environ["GITHUB_REF_NAME"]
    normalized_tag = tag_name[1:] if tag_name.startswith("v") else tag_name

    if normalized_tag != project_version:
        raise SystemExit(
            f"Tag {tag_name!r} does not match pyproject version {project_version!r}."
        )

    print(f"Publishing version {project_version} from tag {tag_name}.")


if __name__ == "__main__":
    main()
