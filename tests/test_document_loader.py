import hashlib
import pytest
from pypdf import PdfWriter

from app.document_loader import calculate_sha256, load_pdf


@pytest.fixture
def sample_pdf(tmp_path):
    path = tmp_path / "sample.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    writer.add_blank_page(width=595, height=842)
    with path.open("wb") as f:
        writer.write(f)
    return path


def test_load_pdf_reads_name_and_page_count(sample_pdf):
    doc = load_pdf(sample_pdf)
    assert doc.file_name == "sample.pdf"
    assert doc.page_count == 2


def test_load_pdf_computes_sha256(sample_pdf):
    doc = load_pdf(sample_pdf)
    expected = hashlib.sha256(sample_pdf.read_bytes()).hexdigest()
    assert doc.sha256 == expected
    assert calculate_sha256(sample_pdf) == expected


def test_load_pdf_rejects_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_pdf(tmp_path / "nope.pdf")


def test_load_pdf_rejects_non_pdf(tmp_path):
    other = tmp_path / "notes.txt"
    other.write_text("not a pdf", encoding="utf-8")
    with pytest.raises(ValueError):
        load_pdf(other)
