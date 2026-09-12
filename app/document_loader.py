"""Read a PDF's basic facts. Nothing else.

The loader is the receiving clerk: it takes the file, reads its bytes once, and
reports the name, size, hash and page count. It does not split questions, call
Gemini, OCR anything, or change the PDF text.
"""

from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
import hashlib

from pypdf import PdfReader


@dataclass
class LoadedDocument:
    file_path: Path
    file_name: str
    sha256: str
    page_count: int
    byte_size: int
    # The file content, read once and reused for hashing, page counting and the
    # Gemini request. repr=False so printing a LoadedDocument does not dump
    # megabytes of PDF to the terminal.
    data: bytes = field(repr=False, default=b"")


def calculate_sha256(file_path: str | Path) -> str:
    """Hash a file on disk in chunks, for files too large to hold in memory."""
    sha = hashlib.sha256()
    with Path(file_path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def load_pdf(file_path: str | Path) -> LoadedDocument:
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Not a PDF file: {path}")

    data = path.read_bytes()

    if not data:
        raise ValueError(f"PDF is empty: {path}")

    reader = PdfReader(BytesIO(data))

    return LoadedDocument(
        file_path=path,
        file_name=path.name,
        sha256=hashlib.sha256(data).hexdigest(),
        page_count=len(reader.pages),
        byte_size=len(data),
        data=data,
    )
