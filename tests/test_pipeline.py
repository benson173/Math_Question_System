"""The pipeline must report failure, not swallow it."""

import json

import pytest

from app.extraction_validator import has_blocking_issues
from app.paths import FAILED_PDF_DIR, PROCESSED_PDF_DIR
from app.pipeline import PdfIngestionPipeline
from app.schemas import ExtractionResult
from scripts.ingest_pdfs import destination_directory, unique_destination


class FakeExtractor:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def extract(self, pdf_path) -> ExtractionResult:
        self.calls.append(pdf_path)
        return self.result


class RecordingRepository:
    def __init__(self):
        self.saved = []

    def save_extraction_result(self, result):
        self.saved.append(result)


@pytest.fixture
def run_pipeline(tmp_path, monkeypatch):
    """Run the pipeline with a fake extractor, exporting into tmp_path."""
    monkeypatch.setattr("app.json_exporter.EXTRACTED_DIR", tmp_path)

    def _run(result):
        repository = RecordingRepository()
        pipeline = PdfIngestionPipeline(
            extractor=FakeExtractor(result),
            repository=repository,
        )
        return pipeline.run_one_pdf("inbox/pdf/sample.pdf"), repository
    return _run


def test_run_one_pdf_returns_the_result(run_pipeline, make_result):
    result, _ = run_pipeline(make_result())
    assert isinstance(result, ExtractionResult)
    assert result.document.file_name == "sample.pdf"


def test_run_one_pdf_fills_in_issues(run_pipeline, make_result, make_document):
    result, _ = run_pipeline(make_result(document=make_document(questions=[])))
    assert [i.issue_code for i in result.issues] == ["NO_QUESTIONS_FOUND"]


def test_clean_run_reports_no_blocking_issues(run_pipeline, make_result):
    result, _ = run_pipeline(make_result())
    assert has_blocking_issues(result.issues) is False


def test_empty_extraction_is_blocking(run_pipeline, make_result, make_document):
    result, _ = run_pipeline(make_result(document=make_document(questions=[])))
    assert has_blocking_issues(result.issues) is True


def test_repository_is_the_only_save_step(run_pipeline, make_result):
    _, repository = run_pipeline(make_result())
    assert len(repository.saved) == 1


def test_export_lands_in_the_configured_directory(tmp_path, run_pipeline, make_result):
    result, _ = run_pipeline(make_result())
    written = list(tmp_path.glob("*.json"))
    assert len(written) == 1
    data = json.loads(written[0].read_text(encoding="utf-8"))
    assert data["source"]["sha256"] == result.source.sha256


def test_failed_extraction_is_still_exported_for_inspection(
    tmp_path, run_pipeline, make_result, make_document
):
    run_pipeline(make_result(document=make_document(questions=[])))
    written = list(tmp_path.glob("*.json"))
    assert len(written) == 1
    data = json.loads(written[0].read_text(encoding="utf-8"))
    assert data["issues"][0]["issue_code"] == "NO_QUESTIONS_FOUND"


# --- batch routing ----------------------------------------------------------

def test_clean_result_goes_to_processed(make_result):
    result = make_result()
    result.issues = []
    assert destination_directory(result) == PROCESSED_PDF_DIR


def test_empty_extraction_goes_to_failed(make_result, make_document):
    from app.extraction_validator import validate_extraction
    result = make_result(document=make_document(questions=[]))
    result.issues = validate_extraction(result.document)
    assert destination_directory(result) == FAILED_PDF_DIR


def test_non_blocking_issues_still_go_to_processed(make_result, make_document, make_question):
    from app.extraction_validator import validate_extraction
    document = make_document([make_question(question_text="Factorise 225x2.")])
    result = make_result(document=document)
    result.issues = validate_extraction(document)
    assert [i.issue_code for i in result.issues] == ["POSSIBLE_BROKEN_POWER"]
    assert destination_directory(result) == PROCESSED_PDF_DIR


def test_unique_destination_avoids_overwriting(tmp_path):
    (tmp_path / "a.pdf").write_bytes(b"first")
    assert unique_destination(tmp_path, "a.pdf").name == "a-2.pdf"

    (tmp_path / "a-2.pdf").write_bytes(b"second")
    assert unique_destination(tmp_path, "a.pdf").name == "a-3.pdf"


def test_unique_destination_uses_the_plain_name_when_free(tmp_path):
    assert unique_destination(tmp_path, "a.pdf").name == "a.pdf"
