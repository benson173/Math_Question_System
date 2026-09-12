"""Compare two runs over the same PDF.

    python -m scripts.compare_extractions              # the two most recent runs
    python -m scripts.compare_extractions a.json b.json

No single run can show that the model transcribed something that is not on the
page: each run is internally consistent. Two runs disagreeing is the signal.
Where they agree the text is very likely right; where they differ, read the
paper.

Every ingestion archives its own JSON under data/history/, so a second run of
the same PDF gives you something to compare against.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.extraction_diff import compare_extractions, render_diff
from app.paths import HISTORY_DIR
from app.schemas import ExtractionResult


def load(path: Path) -> ExtractionResult:
    return ExtractionResult.model_validate(json.loads(path.read_text(encoding="utf-8")))


def two_most_recent() -> tuple[Path, Path]:
    runs = sorted(HISTORY_DIR.rglob("*.json"), key=lambda p: p.stat().st_mtime)
    if len(runs) < 2:
        raise SystemExit(
            f"Need two archived runs to compare; found {len(runs)} in {HISTORY_DIR}.\n"
            "Ingest the same PDF twice, then run this again."
        )
    older, newer = runs[-2], runs[-1]
    if older.parent != newer.parent:
        raise SystemExit(
            "The two most recent runs are of different PDFs:\n"
            f"  {older}\n  {newer}\n"
            "Pass the two files to compare explicitly."
        )
    return older, newer


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv

    if len(args) == 2:
        before_path, after_path = Path(args[0]), Path(args[1])
    elif not args:
        before_path, after_path = two_most_recent()
    else:
        raise SystemExit("Pass two JSON files, or none to use the two most recent runs.")

    before, after = load(before_path), load(after_path)

    if before.source and after.source and before.source.sha256 != after.source.sha256:
        print("Warning: these runs are of different PDFs "
              f"({before.source.sha256[:12]} vs {after.source.sha256[:12]}).\n")

    diff = compare_extractions(before, after)
    print(render_diff(diff, str(before_path), str(after_path)), end="")
    return 0 if diff.is_clean else 1


if __name__ == "__main__":
    raise SystemExit(main())
