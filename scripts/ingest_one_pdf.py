"""Ingest one PDF.

    python -m scripts.ingest_one_pdf                      # the PDF waiting in the inbox
    python -m scripts.ingest_one_pdf path/to/paper.pdf

Exits non-zero when the PDF produced no usable questions, so it can be used in
a shell pipeline or a Makefile.

With no argument it takes inbox/pdf/sample.pdf, or the single PDF in the inbox
if there is exactly one. A successful ingestion moves the PDF to processed/pdf/,
so running this twice in a row without an argument is expected to report that
there is nothing left to do rather than failing obscurely.
"""

from __future__ import annotations

from pathlib import Path
import sys

from app.extraction_validator import blocking_issues
from app.paths import FAILED_PDF_DIR, INBOX_PDF_DIR, PROCESSED_PDF_DIR
from app.pipeline import PdfIngestionPipeline
from app.repository import Repository


DEFAULT_NAME = "sample.pdf"
MAX_LISTED = 10


def pdfs_in(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(p for p in directory.rglob("*")
                  if p.is_file() and p.suffix.lower() == ".pdf")


def _already_filed(name: str) -> str:
    """Tell the user where a PDF of this name went, if a previous run moved it."""
    for label, directory in (("processed", PROCESSED_PDF_DIR), ("failed", FAILED_PDF_DIR)):
        for path in pdfs_in(directory):
            if path.name == name:
                return (f"A file named {name} is already in {label}/pdf/ - an earlier run "
                        f"moved it there.\nTo ingest it again:\n"
                        f"    python -m scripts.ingest_one_pdf {path}")
    return ""


def resolve_pdf(args: list[str]) -> Path:
    """Find the PDF to ingest, or explain what to do instead."""
    if args:
        path = Path(args[0])
        if path.exists():
            return path
        message = f"PDF not found: {path}"
        hint = _already_filed(path.name)
        raise SystemExit(f"{message}\n\n{hint}" if hint else message)

    default = INBOX_PDF_DIR / DEFAULT_NAME
    if default.exists():
        return default

    waiting = pdfs_in(INBOX_PDF_DIR)
    if len(waiting) == 1:
        print(f"Using the only PDF in the inbox: {waiting[0].name}")
        return waiting[0]

    if waiting:
        listed = "\n".join(f"    {p}" for p in waiting[:MAX_LISTED])
        extra = f"\n    ... and {len(waiting) - MAX_LISTED} more" \
            if len(waiting) > MAX_LISTED else ""
        raise SystemExit(
            f"{len(waiting)} PDFs are waiting in {INBOX_PDF_DIR}. Name one:\n"
            f"{listed}{extra}\n\nOr ingest them all:\n"
            "    python -m scripts.ingest_pdfs"
        )

    hint = _already_filed(DEFAULT_NAME)
    raise SystemExit(
        f"No PDFs in {INBOX_PDF_DIR}.\n\n"
        + (hint + "\n\n" if hint else "")
        + "Put a PDF there and run this again, or name one directly:\n"
        "    python -m scripts.ingest_one_pdf path/to/paper.pdf"
    )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    pdf_path = resolve_pdf(args)

    repository = Repository()
    print(repository.describe_target())
    pipeline = PdfIngestionPipeline(repository=repository)
    result = pipeline.run_one_pdf(pdf_path)

    return 1 if blocking_issues(result.issues) else 0


if __name__ == "__main__":
    raise SystemExit(main())
