"""Finding the PDF to ingest, and saying something useful when there isn't one.

A successful ingestion moves the PDF to processed/pdf/, so the second run of
`python -m scripts.ingest_one_pdf` with no argument finds nothing. That used to
surface as a FileNotFoundError traceback naming a path the user never typed.
"""

from __future__ import annotations

import pytest

import scripts.ingest_one_pdf as single


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    paths = {name: tmp_path / name for name in ("inbox", "processed", "failed")}
    for path in paths.values():
        path.mkdir()
    monkeypatch.setattr(single, "INBOX_PDF_DIR", paths["inbox"])
    monkeypatch.setattr(single, "PROCESSED_PDF_DIR", paths["processed"])
    monkeypatch.setattr(single, "FAILED_PDF_DIR", paths["failed"])
    return paths


def write(directory, name):
    path = directory / name
    path.write_bytes(b"%PDF-1.4")
    return path


def failure_message(args) -> str:
    with pytest.raises(SystemExit) as exit_info:
        single.resolve_pdf(args)
    return str(exit_info.value)


# --- the happy paths --------------------------------------------------------

def test_the_default_sample_is_used_when_present(dirs):
    expected = write(dirs["inbox"], "sample.pdf")
    write(dirs["inbox"], "other.pdf")
    assert single.resolve_pdf([]) == expected


def test_a_named_path_is_used_as_given(dirs):
    path = write(dirs["inbox"], "x.pdf")
    assert single.resolve_pdf([str(path)]) == path


def test_a_lone_pdf_is_used_even_under_another_name(dirs, capsys):
    expected = write(dirs["inbox"], "2024-dse-paper1.pdf")
    assert single.resolve_pdf([]) == expected
    assert "only PDF in the inbox" in capsys.readouterr().out


# --- nothing to do ----------------------------------------------------------

def test_an_empty_inbox_explains_what_to_do(dirs):
    message = failure_message([])
    assert "No PDFs in" in message
    assert "path/to/paper.pdf" in message


def test_a_paper_moved_to_processed_is_pointed_at(dirs):
    write(dirs["processed"], "sample.pdf")
    message = failure_message([])
    assert "already in processed/pdf/" in message
    assert "scripts.ingest_one_pdf" in message


def test_a_paper_moved_to_failed_is_pointed_at(dirs):
    write(dirs["failed"], "broken.pdf")
    assert "already in failed/pdf/" in failure_message(["broken.pdf"])


def test_a_genuinely_missing_path_says_so_plainly(dirs):
    assert failure_message(["/nowhere/ghost.pdf"]).startswith("PDF not found")


# --- several to choose from -------------------------------------------------

def test_several_pdfs_are_listed(dirs):
    for n in range(1, 4):
        write(dirs["inbox"], f"paper{n}.pdf")

    message = failure_message([])
    assert "3 PDFs are waiting" in message
    assert all(f"paper{n}.pdf" in message for n in (1, 2, 3))
    assert "scripts.ingest_pdfs" in message


def test_a_long_list_is_truncated(dirs):
    for n in range(1, 26):
        write(dirs["inbox"], f"paper{n:02d}.pdf")

    message = failure_message([])
    assert "and 15 more" in message
    assert message.count(".pdf\n") <= single.MAX_LISTED + 1


def test_subfolders_are_searched(dirs):
    nested = dirs["inbox"] / "2024"
    nested.mkdir()
    expected = write(nested, "paper.pdf")
    assert single.resolve_pdf([]) == expected


def test_uppercase_suffixes_are_found(dirs):
    expected = write(dirs["inbox"], "PAPER.PDF")
    assert single.resolve_pdf([]) == expected
