import pytest
from pypdf import PdfWriter

from app.schemas import (
    ExtractedDocument,
    ExtractedQuestion,
    ExtractionResult,
    ExtractionRun,
    SourceDocument,
)


@pytest.fixture
def make_question():
    def _make(**overrides) -> ExtractedQuestion:
        defaults = dict(
            source_question_id="1",
            page_start=1,
            page_end=1,
            question_text="Factorise 1 - 225x².",
        )
        defaults.update(overrides)
        return ExtractedQuestion(**defaults)
    return _make


@pytest.fixture
def make_document(make_question):
    def _make(questions=None, page_count=1, file_name="sample.pdf") -> ExtractedDocument:
        if questions is None:
            questions = [make_question()]
        return ExtractedDocument(
            file_name=file_name,
            page_count=page_count,
            questions=questions,
        )
    return _make


@pytest.fixture
def make_result(make_document):
    def _make(document=None, issues=None, sha256="a" * 64) -> ExtractionResult:
        document = document or make_document()
        return ExtractionResult(
            document=document,
            issues=issues or [],
            source=SourceDocument(
                file_name=document.file_name,
                sha256=sha256,
                page_count=document.page_count,
                byte_size=1234,
            ),
            run=ExtractionRun(
                run_id="run123456789",
                extracted_at="2026-09-12T00:00:00+00:00",
                extraction_version="QEE_v1",
                question_object_version="QOS_v1",
                model="test-model",
            ),
        )
    return _make


@pytest.fixture
def write_pdf(tmp_path):
    def _write(name="sample.pdf", pages=1):
        path = tmp_path / name
        writer = PdfWriter()
        for _ in range(pages):
            writer.add_blank_page(width=595, height=842)
        with path.open("wb") as f:
            writer.write(f)
        return path
    return _write
