"""Ingest every PDF in inbox/pdf/.

A PDF lands in processed/pdf/ only if it ingested cleanly. A PDF that raised an
error OR produced a blocking validation issue (no questions found, a question
with empty text) lands in failed/pdf/ - otherwise an empty extraction would look
like a success and the original would be filed away as done.
"""

from pathlib import Path
import shutil

from app.extraction_validator import blocking_issues
from app.paths import FAILED_PDF_DIR, INBOX_PDF_DIR, PROCESSED_PDF_DIR
from app.pipeline import PdfIngestionPipeline


MAX_NAME_COLLISIONS = 1000


def unique_destination(directory: Path, file_name: str) -> Path:
    """A path in `directory` that does not overwrite an existing file."""
    candidate = directory / file_name
    if not candidate.exists():
        return candidate

    stem, suffix = Path(file_name).stem, Path(file_name).suffix
    for n in range(2, MAX_NAME_COLLISIONS):
        candidate = directory / f"{stem}-{n}{suffix}"
        if not candidate.exists():
            return candidate

    raise RuntimeError(f"Too many files named {file_name} in {directory}")


def destination_directory(result) -> Path:
    """processed/ only for a clean ingestion; failed/ for a blocking issue.

    This is the rule that stops an extraction with zero questions from being
    filed away as a success.
    """
    return FAILED_PDF_DIR if blocking_issues(result.issues) else PROCESSED_PDF_DIR


def _file_away(pdf_path: Path, directory: Path) -> Path:
    destination = unique_destination(directory, pdf_path.name)
    shutil.move(str(pdf_path), str(destination))
    return destination


def main() -> int:
    for directory in (INBOX_PDF_DIR, PROCESSED_PDF_DIR, FAILED_PDF_DIR):
        directory.mkdir(parents=True, exist_ok=True)

    pdf_files = sorted(INBOX_PDF_DIR.glob("*.pdf"))

    if not pdf_files:
        print("No PDF files found.")
        return 0

    pipeline = PdfIngestionPipeline()
    succeeded: list[str] = []
    failed: list[tuple[str, str]] = []

    for pdf_path in pdf_files:
        print("=" * 60)
        print("Processing:", pdf_path.name)

        try:
            result = pipeline.run_one_pdf(pdf_path)
        except Exception as exc:
            print("Failed:", exc)
            _file_away(pdf_path, FAILED_PDF_DIR)
            failed.append((pdf_path.name, f"{type(exc).__name__}: {exc}"))
            print("Moved to failed.")
            continue

        destination = destination_directory(result)
        _file_away(pdf_path, destination)

        if destination == FAILED_PDF_DIR:
            codes = ", ".join(sorted(
                {issue.issue_code for issue in blocking_issues(result.issues)}))
            failed.append((pdf_path.name, codes))
            print("Moved to failed.")
        else:
            succeeded.append(pdf_path.name)
            print("Moved to processed.")

    print("=" * 60)
    print(f"SUMMARY   processed: {len(succeeded)}   failed: {len(failed)}")
    for name in succeeded:
        print("  OK      ", name)
    for name, reason in failed:
        print("  FAILED  ", name, "-", reason)

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
