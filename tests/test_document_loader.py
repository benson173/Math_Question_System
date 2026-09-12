import hashlib
import pytest

from app.document_loader import calculate_sha256, load_pdf


def test_load_pdf_reads_name_and_page_count(write_pdf):
    doc = load_pdf(write_pdf(pages=2))
    assert doc.file_name == "sample.pdf"
    assert doc.page_count == 2


def test_load_pdf_computes_sha256_and_size(write_pdf):
    path = write_pdf()
    doc = load_pdf(path)
    raw = path.read_bytes()
    assert doc.sha256 == hashlib.sha256(raw).hexdigest()
    assert doc.byte_size == len(raw)


def test_load_pdf_keeps_the_bytes_for_reuse(write_pdf):
    path = write_pdf()
    doc = load_pdf(path)
    assert doc.data == path.read_bytes()


def test_chunked_hash_matches_whole_file_hash(write_pdf):
    path = write_pdf()
    assert calculate_sha256(path) == hashlib.sha256(path.read_bytes()).hexdigest()


def test_repr_does_not_dump_the_pdf_bytes(write_pdf):
    doc = load_pdf(write_pdf())
    assert "data=" not in repr(doc)


def test_load_pdf_rejects_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_pdf(tmp_path / "nope.pdf")


def test_load_pdf_rejects_non_pdf(tmp_path):
    other = tmp_path / "notes.txt"
    other.write_text("not a pdf", encoding="utf-8")
    with pytest.raises(ValueError):
        load_pdf(other)


def test_load_pdf_rejects_empty_file(tmp_path):
    empty = tmp_path / "empty.pdf"
    empty.write_bytes(b"")
    with pytest.raises(ValueError):
        load_pdf(empty)
