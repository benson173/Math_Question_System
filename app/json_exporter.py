"""Write an extraction to disk as JSON, for eyeballing before Supabase exists."""

from __future__ import annotations

from pathlib import Path
import json

from app.paths import DIAGRAMS_DIR, EXTRACTED_DIR, HISTORY_DIR, safe_stem
from app.schemas import ExtractionResult


def extraction_output_path(result: ExtractionResult) -> Path:
    """Where this extraction's JSON belongs.

    Named by content hash, not just file name: two different papers both called
    "sample.pdf" no longer overwrite each other, while re-ingesting the same PDF
    deliberately overwrites its own previous output.
    """
    stem = safe_stem(result.document.file_name)
    digest = result.source.sha256[:12] if result.source else "nohash"
    return EXTRACTED_DIR / f"{stem}-{digest}.json"


def diagram_output_dir(result: ExtractionResult) -> Path:
    """One folder per extraction, named like its JSON so the two line up."""
    return DIAGRAMS_DIR / extraction_output_path(result).stem


def history_output_path(result: ExtractionResult) -> Path:
    """Where this run is archived, so later runs can be compared against it.

    The main JSON is overwritten each time the same PDF is ingested - that is
    what makes it idempotent. Keeping every run under its run id is what makes
    the model's inconsistency visible at all.
    """
    stem = extraction_output_path(result).stem
    run_id = result.run.run_id if result.run else "norun"
    return HISTORY_DIR / stem / f"{run_id}.json"


def export_extraction_json(
    result: ExtractionResult,
    output_path: str | Path,
) -> Path:
    output = {
        "source": result.source.model_dump() if result.source else None,
        "run": result.run.model_dump() if result.run else None,
        "document": result.document.model_dump(),
        "issues": [issue.model_dump() for issue in result.issues],
        "diagrams": [asset.model_dump() for asset in result.diagrams],
    }

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path
