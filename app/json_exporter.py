from pathlib import Path
import json
from app.schemas import ExtractedDocument, ValidationIssue


def export_extraction_json(
    document: ExtractedDocument,
    issues: list[ValidationIssue],
    output_path: str | Path,
) -> None:
    output = {
        "document": document.model_dump(),
        "issues": [issue.model_dump() for issue in issues],
    }

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
