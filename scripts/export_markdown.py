"""Rebuild the Markdown report from a saved extraction JSON.

    python -m scripts.export_markdown                 # newest extraction
    python -m scripts.export_markdown path/to/x.json

Useful after editing a JSON by hand, or to regenerate a report that was
deleted. Does not call Gemini.
"""

from __future__ import annotations

import sys
from pathlib import Path

from app.extraction_io import load_extraction
from app.markdown_exporter import export_extraction_markdown, markdown_output_path
from app.paths import EXTRACTED_DIR


def newest_json() -> Path:
    files = sorted(EXTRACTED_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime)
    if not files:
        raise SystemExit(f"No extraction JSON in {EXTRACTED_DIR}")
    return files[-1]


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    json_path = Path(args[0]) if args else newest_json()

    result = load_extraction(json_path)

    report_path = export_extraction_markdown(result, markdown_output_path(json_path))
    print("Wrote:", report_path)
    print(f"({report_path.stat().st_size:,} bytes, "
          f"{len(result.document.questions)} questions, "
          f"{len(result.diagrams)} diagrams)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
