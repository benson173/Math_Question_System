"""Attach a marking scheme to a paper that was already ingested.

    python3 -m scripts.attach_marking_scheme S4-2024-mock-ms.pdf
    python3 -m scripts.attach_marking_scheme path/to/scheme.pdf data/extracted/S4-2024-mock-b584940bfebb.json

With one argument the paper is found by name: <stem>-ms.pdf looks for the
newest data/extracted/<stem>-*.json. Answers are merged into the questions,
saved as a new run, and the JSON, report and database are updated. The
paper's PDF is not needed and images are not re-rendered.

The batch does the same thing automatically for any <stem>-ms.pdf in the
inbox, whether or not its paper is in the same batch.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

from app.marking_scheme import marking_scheme_stem
from app.paths import EXTRACTED_DIR, safe_stem
from app.pipeline import PdfIngestionPipeline
from app.repository import Repository
from app.schemas import ExtractionResult


def find_extraction_for(scheme_path: Path) -> Path | None:
    """The newest saved extraction whose file name matches the scheme's stem."""
    stem = marking_scheme_stem(scheme_path.name)
    if stem is None:
        return None
    candidates = sorted(EXTRACTED_DIR.glob(f"{safe_stem(stem + '.pdf')}-*.json"),
                        key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def load_result(path: Path) -> ExtractionResult:
    return ExtractionResult.model_validate(json.loads(path.read_text(encoding="utf-8")))


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(__doc__)
        return 2

    scheme_path = Path(args[0])
    if not scheme_path.exists():
        print(f"Marking scheme not found: {scheme_path}")
        return 2

    if len(args) > 1:
        json_path = Path(args[1])
    else:
        json_path = find_extraction_for(scheme_path)
        if json_path is None:
            stem = marking_scheme_stem(scheme_path.name) or scheme_path.stem
            print(f"No extraction found for {stem}. Ingest the paper first, or name "
                  f"its JSON as the second argument.")
            return 1

    if not json_path.exists():
        print(f"Extraction not found: {json_path}")
        return 2

    print(f"Paper:          {json_path}")
    print(f"Marking scheme: {scheme_path}")
    repository = Repository()
    print(repository.describe_target())

    pipeline = PdfIngestionPipeline(repository=repository)
    result = pipeline.attach_marking_scheme(load_result(json_path), scheme_path)
    scheme = result.document.marking_scheme
    return 0 if scheme and scheme.matched else 1


if __name__ == "__main__":
    raise SystemExit(main())
