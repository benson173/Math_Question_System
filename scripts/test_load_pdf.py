"""Check that a PDF can be read at all. Needs no API key."""

import sys

from app.document_loader import load_pdf
from app.paths import INBOX_PDF_DIR


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    pdf_path = args[0] if args else INBOX_PDF_DIR / "sample.pdf"

    doc = load_pdf(pdf_path)

    print("File:", doc.file_name)
    print("Pages:", doc.page_count)
    print("Size:", doc.byte_size, "bytes")
    print("SHA256:", doc.sha256)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
