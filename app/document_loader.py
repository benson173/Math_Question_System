from dataclasses import dataclass
from pathlib import Path
import hashlib
from pypdf import PdfReader


@dataclass
class LoadedDocument:
    file_path: Path
    file_name: str
    sha256: str
    page_count: int


def calculate_sha256(file_path: Path) -> str:
    sha = hashlib.sha256()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def load_pdf(file_path: str | Path) -> LoadedDocument:
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Not a PDF file: {path}")

    reader = PdfReader(str(path))

    return LoadedDocument(
        file_path=path,
        file_name=path.name,
        sha256=calculate_sha256(path),
        page_count=len(reader.pages),
    )
