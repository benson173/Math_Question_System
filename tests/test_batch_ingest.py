"""Ingesting a whole inbox: discovery, dedupe, filing and reporting."""

from __future__ import annotations

import hashlib
import shutil

import pytest

import scripts.ingest_pdfs as batch
from app.extraction_validator import validate_extraction
from app.schemas import ExtractedDocument, ExtractedQuestion, ExtractionResult


def pdfs_in(directory):
    return {p.name for p in directory.rglob("*") if p.suffix.lower() == ".pdf"}


@pytest.fixture
def inbox(tmp_path, monkeypatch):
    """A self-contained inbox/processed/failed/extracted set."""
    paths = {name: tmp_path / name
             for name in ("inbox", "processed", "failed", "extracted")}
    for path in paths.values():
        path.mkdir()

    monkeypatch.setattr(batch, "INBOX_PDF_DIR", paths["inbox"])
    monkeypatch.setattr(batch, "PROCESSED_PDF_DIR", paths["processed"])
    monkeypatch.setattr(batch, "FAILED_PDF_DIR", paths["failed"])
    monkeypatch.setattr(batch, "EXTRACTED_DIR", paths["extracted"])
    return paths


@pytest.fixture
def fake_pipeline(monkeypatch):
    """A pipeline that extracts three questions, or misbehaves on cue."""
    calls = []

    class FakePipeline:
        def __init__(self, *args, **kwargs):
            pass

        def run_one_pdf(self, path):
            calls.append(path)
            data = path.read_bytes()
            if data == b"BOOM":
                raise RuntimeError("Gemini exploded")
            count = 0 if data == b"ZERO" else 3
            questions = [
                ExtractedQuestion(source_question_id=str(n + 1), page_start=1,
                                  page_end=1, question_text=f"題 {n + 1}")
                for n in range(count)
            ]
            document = ExtractedDocument(level="F4", file_name=path.name, page_count=1,
                                         questions=questions)
            return ExtractionResult(document=document,
                                    issues=validate_extraction(document))

    monkeypatch.setattr(batch, "PdfIngestionPipeline", FakePipeline)
    monkeypatch.setattr(batch, "Repository", lambda verbose=True: None)
    return calls


def write(inbox, relative, content):
    path = inbox["inbox"] / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


# --- discovery --------------------------------------------------------------

def test_find_pdfs_covers_subfolders_and_uppercase(inbox):
    write(inbox, "a.pdf", b"A")
    write(inbox, "UPPER.PDF", b"B")
    write(inbox, "2024/nested.pdf", b"C")
    write(inbox, "2024/deep/deeper.pdf", b"D")
    write(inbox, "notes.txt", b"not a pdf")

    found = {p.name for p in batch.find_pdfs(inbox["inbox"])}
    assert found == {"a.pdf", "UPPER.PDF", "nested.pdf", "deeper.pdf"}


def test_an_empty_inbox_is_not_an_error(inbox, fake_pipeline):
    assert batch.main([]) == 0
    assert fake_pipeline == []


# --- filing -----------------------------------------------------------------

def test_clean_papers_go_to_processed_and_failures_to_failed(inbox, fake_pipeline):
    write(inbox, "good.pdf", b"AAA")
    write(inbox, "boom.pdf", b"BOOM")
    write(inbox, "empty.pdf", b"ZERO")

    assert batch.main([]) == 1
    assert pdfs_in(inbox["processed"]) == {"good.pdf"}
    assert pdfs_in(inbox["failed"]) == {"boom.pdf", "empty.pdf"}
    assert pdfs_in(inbox["inbox"]) == set()


def test_folder_structure_is_preserved(inbox, fake_pipeline):
    write(inbox, "2024/deep/paper.pdf", b"AAA")
    batch.main([])
    assert (inbox["processed"] / "2024" / "deep" / "paper.pdf").exists()
    assert not (inbox["inbox"] / "2024").exists()


def test_keep_leaves_the_inbox_alone(inbox, fake_pipeline):
    write(inbox, "a.pdf", b"AAA")
    batch.main(["--keep"])
    assert pdfs_in(inbox["inbox"]) == {"a.pdf"}
    assert pdfs_in(inbox["processed"]) == set()


# --- not paying twice -------------------------------------------------------

def test_two_copies_of_one_paper_are_extracted_once(inbox, fake_pipeline):
    write(inbox, "a.pdf", b"AAA")
    write(inbox, "a-copy.pdf", b"AAA")

    batch.main([])
    assert len(fake_pipeline) == 1
    assert pdfs_in(inbox["processed"]) == {"a.pdf", "a-copy.pdf"}


def test_an_already_ingested_paper_is_skipped(inbox, fake_pipeline):
    content = b"AAA"
    digest = hashlib.sha256(content).hexdigest()
    (inbox["extracted"] / f"a-{digest[:12]}.json").write_text("{}", encoding="utf-8")
    write(inbox, "a.pdf", content)

    assert batch.main([]) == 0
    assert fake_pipeline == []
    assert pdfs_in(inbox["processed"]) == {"a.pdf"}


def test_a_renamed_copy_is_recognised_by_content(inbox, fake_pipeline):
    content = b"AAA"
    digest = hashlib.sha256(content).hexdigest()
    (inbox["extracted"] / f"original-{digest[:12]}.json").write_text("{}", encoding="utf-8")
    write(inbox, "renamed.pdf", content)

    batch.main([])
    assert fake_pipeline == []


def test_redo_ingests_anyway(inbox, fake_pipeline):
    content = b"AAA"
    digest = hashlib.sha256(content).hexdigest()
    (inbox["extracted"] / f"a-{digest[:12]}.json").write_text("{}", encoding="utf-8")
    write(inbox, "a.pdf", content)

    batch.main(["--redo"])
    assert len(fake_pipeline) == 1


# --- reporting --------------------------------------------------------------

def test_a_batch_report_records_every_paper(inbox, fake_pipeline):
    write(inbox, "good.pdf", b"AAA")
    write(inbox, "copy.pdf", b"AAA")
    write(inbox, "boom.pdf", b"BOOM")

    batch.main([])
    reports = list(inbox["extracted"].glob("batch-*.md"))
    assert len(reports) == 1

    text = reports[0].read_text(encoding="utf-8")
    for name in ("good.pdf", "copy.pdf", "boom.pdf"):
        assert name in text
    assert "duplicate" in text and "failed" in text


def test_two_batches_do_not_overwrite_each_others_report(inbox, fake_pipeline):
    write(inbox, "a.pdf", b"AAA")
    batch.main([])
    write(inbox, "b.pdf", b"BBB")
    batch.main([])
    assert len(list(inbox["extracted"].glob("batch-*.md"))) == 2


@pytest.mark.parametrize("seconds, expected", [
    (5, "5s"), (59.4, "59s"), (60, "1m00s"), (3725, "62m05s"),
])
def test_format_duration(seconds, expected):
    assert batch.format_duration(seconds) == expected


# --- filing helpers ---------------------------------------------------------

def test_unique_destination_never_overwrites(tmp_path):
    assert batch.unique_destination(tmp_path, "a.pdf").name == "a.pdf"
    (tmp_path / "a.pdf").write_bytes(b"1")
    assert batch.unique_destination(tmp_path, "a.pdf").name == "a-2.pdf"


def test_prune_empty_directories(tmp_path):
    (tmp_path / "a" / "b" / "c").mkdir(parents=True)
    (tmp_path / "keep").mkdir()
    (tmp_path / "keep" / "f.txt").write_text("x", encoding="utf-8")
    batch.prune_empty_directories(tmp_path)
    assert not (tmp_path / "a").exists()
    assert (tmp_path / "keep" / "f.txt").exists()
