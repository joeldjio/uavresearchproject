"""Analyze a SkyMeshX trace bundle and write a Markdown summary."""

from __future__ import annotations

import argparse
from pathlib import Path

from skymeshx.core.trace_logger import analyze_trace_bundle, format_markdown_report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", help="Path to trace_runs/<timestamp>_<scenario>/")
    parser.add_argument(
        "-o",
        "--output",
        help="Markdown output path. Defaults to <bundle>/trace_summary.md",
    )
    args = parser.parse_args()

    bundle = Path(args.bundle)
    if not bundle.exists():
        parser.error(f"Trace bundle does not exist: {bundle}")
    if not (bundle / "manifest.json").exists():
        parser.error(f"Trace bundle has no manifest.json: {bundle}")

    summary = analyze_trace_bundle(bundle)
    markdown = format_markdown_report(summary)
    output = Path(args.output) if args.output else bundle / "trace_summary.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown, encoding="utf-8")
    print(str(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
