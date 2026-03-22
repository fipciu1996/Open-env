"""Build static coverage site assets used by the CI workflow."""

from __future__ import annotations

import json
from pathlib import Path
import shutil


INDEX_HTML = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Open-env Coverage</title>
    <style>
      body {
        font-family: Arial, sans-serif;
        margin: 3rem auto;
        max-width: 48rem;
        padding: 0 1rem;
        line-height: 1.6;
      }
      .badge-link {
        font-weight: 700;
      }
    </style>
  </head>
  <body>
    <h1>Open-env Coverage</h1>
    <p>This site publishes the latest GitHub Actions coverage report.</p>
    <ul>
      <li><a class="badge-link" href="./coverage/index.html">Open HTML coverage report</a></li>
      <li><a href="./coverage.svg">Open coverage badge</a></li>
    </ul>
  </body>
</html>
"""


def build_index(site_dir: Path) -> None:
    """Write the landing page for the published coverage site."""
    site_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / "index.html").write_text(INDEX_HTML, encoding="utf-8")


def copy_html_report(source_dir: Path, target_dir: Path) -> None:
    """Copy the generated HTML coverage report into the publish directory."""
    if target_dir.exists():
        shutil.rmtree(target_dir)
    shutil.copytree(source_dir, target_dir)


def write_summary(coverage_json: Path, output_path: Path) -> None:
    """Create the Markdown summary that is appended to the workflow summary."""
    coverage = json.loads(coverage_json.read_text(encoding="utf-8"))
    total = coverage["totals"]["percent_covered_display"]
    output_path.write_text(
        "\n".join(
            [
                "## Coverage Summary",
                "",
                f"- Total coverage: **{total}%**",
                "- Documentation build is validated in CI.",
                "- The HTML coverage report is published via GitHub Pages on pushes to `main`.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> None:
    """Create the static coverage site layout expected by the CI workflow."""
    site_dir = Path("site")
    coverage_dir = site_dir / "coverage"

    build_index(site_dir)
    copy_html_report(Path("htmlcov"), coverage_dir)
    write_summary(Path("coverage.json"), Path(".coverage-summary.md"))


if __name__ == "__main__":
    main()
