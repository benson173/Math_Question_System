import pytest
from pydantic import ValidationError

from app.schemas import (
    ExtractedDocument,
    ExtractedQuestion,
    ExtractionResult,
    QuestionExtractionPayload,
    ValidationIssue,
)


def test_question_defaults(make_question):
    q = make_question()
    assert q.marks is None
    assert q.answer is None
    assert q.worked_solution is None
    assert q.diagram_required is False
    assert q.extraction_notes == []


def test_question_requires_text():
    with pytest.raises(ValidationError):
        ExtractedQuestion(source_question_id="1", page_start=1, page_end=1)


def test_extraction_payload_carries_questions_and_the_printed_level_and_module():
    assert set(QuestionExtractionPayload.model_fields) == {"questions", "level_text",
                                                           "module_text"}


def test_payload_does_not_ask_the_model_for_document_facts():
    # file_name / page_count come from the PDF, never from Gemini.
    for field in ("file_name", "page_count"):
        assert field in ExtractedDocument.model_fields
        assert field not in QuestionExtractionPayload.model_fields


def test_issue_rejects_unknown_severity():
    with pytest.raises(ValidationError):
        ValidationIssue(issue_code="X", severity="catastrophic", message="m")


@pytest.mark.parametrize("severity", ["critical", "high", "medium", "low"])
def test_issue_accepts_known_severities(severity):
    assert ValidationIssue(issue_code="X", severity=severity, message="m").severity == severity


def test_issue_question_id_is_optional():
    assert ValidationIssue(issue_code="X", severity="low", message="m").source_question_id is None


def test_result_defaults(make_document):
    result = ExtractionResult(document=make_document())
    assert result.issues == []
    assert result.source is None
    assert result.run is None


def test_result_carries_provenance(make_result):
    result = make_result()
    assert result.source.sha256 == "a" * 64
    assert result.run.run_id == "run123456789"
