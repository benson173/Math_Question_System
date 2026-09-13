"""See which kinds of question the extractor struggles with, across papers.

    python -m scripts.analyse_extractions              # everything in data/extracted
    python -m scripts.analyse_extractions a.json b.json

One paper tells you whether that paper came out right. Several papers, grouped
by what each question contains - a table, a diagram, sub-parts, LaTeX - tell you
which kinds of question to distrust. Ingest a varied set, then run this.

Writes data/extracted/analysis-<timestamp>.md as well as printing.
"""

from __future__ import annotations

from datetime import datetime, timezone
import sys
from pathlib import Path

from app.extraction_io import load_extractions
from app.extraction_stats import analyse, render_analysis
from app.paths import EXTRACTED_DIR
from app.schemas import ExtractionResult


def load_results(paths: list[Path]) -> list[ExtractionResult]:
    return [result for _, result in load_extractions(
        paths, on_skip=lambda path, exc: print(
            f"Skipping {path.name}: {type(exc).__name__}: {exc}", file=sys.stderr))]


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv

    if args:
        paths = [Path(a) for a in args]
    else:
        paths = sorted(p for p in EXTRACTED_DIR.glob("*.json"))

    if not paths:
        raise SystemExit(f"No extraction JSON found in {EXTRACTED_DIR}.")

    results = load_results(paths)
    if not results:
        raise SystemExit("None of those files could be read as an extraction.")

    report = render_analysis(analyse(results))
    print(report, end="")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = EXTRACTED_DIR / f"analysis-{stamp}.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    print(f"\nWrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
