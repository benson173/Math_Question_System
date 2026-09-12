"""Ingest one PDF.

    python -m scripts.ingest_one_pdf                      # inbox/pdf/sample.pdf
    python -m scripts.ingest_one_pdf path/to/paper.pdf

Exits non-zero when the PDF produced no usable questions, so it can be used in
a shell pipeline or a Makefile.
"""

from __future__ import annotations

import sys

from app.extraction_validator import blocking_issues
from app.paths import INBOX_PDF_DIR
from app.pipeline import PdfIngestionPipeline


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    pdf_path = args[0] if args else INBOX_PDF_DIR / "sample.pdf"

    pipeline = PdfIngestionPipeline()
    result = pipeline.run_one_pdf(pdf_path)

    return 1 if blocking_issues(result.issues) else 0


if __name__ == "__main__":
    raise SystemExit(main())
