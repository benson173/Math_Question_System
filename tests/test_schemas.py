import pytest
from pydantic import ValidationError

from app.schemas import ExtractedDocument, ExtractedQuestion, ExtractionResult


def test_question_defaults():
    q = ExtractedQuestion(
        source_question_id="1",
        page_start=1,
        page_end=1,
        question_text="Factorise 1 - 225x².",
    )
    assert q.marks is None
    assert q.answer is None
    assert q.worked_solution is None
    assert q.diagram_required is False
    assert q.extraction_notes == []


def test_question_requires_text():
    with pytest.raises(ValidationError):
        ExtractedQuestion(source_question_id="1", page_start=1, page_end=1)


def test_extraction_result_defaults_to_no_issues():
    document = ExtractedDocument(file_name="sample.pdf", page_count=1, questions=[])
    assert ExtractionResult(document=document).issues == []
