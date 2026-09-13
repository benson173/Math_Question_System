"""Read a saved extraction back from its JSON.

One loader for every script that starts from data/extracted/*.json - pushing
to the database, attaching a marking scheme, comparing runs, cross-paper
statistics - so a change to the file format is made in one place.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Optional

from app.schemas import ExtractionResult


def load_extraction(path: str | Path) -> ExtractionResult:
    return ExtractionResult.model_validate(
        json.loads(Path(path).read_text(encoding="utf-8")))


def load_extractions(paths, on_skip: Optional[Callable[[Path, Exception], None]] = None
                     ) -> list[tuple[Path, ExtractionResult]]:
    """Every file that is an extraction, with its path; the rest are skipped.

    A batch report or an analysis JSON in the same folder is not an error,
    just not an extraction, so it is reported to `on_skip` and passed over.
    """
    loaded = []
    for path in sorted(Path(p) for p in paths):
        try:
            loaded.append((path, load_extraction(path)))
        except Exception as exc:
            if on_skip:
                on_skip(path, exc)
    return loaded
