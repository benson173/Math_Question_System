import json

from app.json_exporter import export_extraction_json
from app.schemas import ExtractedDocument, ExtractedQuestion, ValidationIssue


def test_export_writes_document_and_issues(tmp_path):
    document = ExtractedDocument(
        file_name="sample.pdf",
        page_count=1,
        questions=[
            ExtractedQuestion(
                source_question_id="1",
                page_start=1,
                page_end=1,
                question_text="Factorise 1 - 225x².",
                marks=2,
            )
        ],
    )
    issues = [ValidationIssue(issue_code="X", severity="low", message="note")]

    output_path = tmp_path / "nested" / "sample.pdf.json"
    export_extraction_json(document, issues, output_path)

    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data["document"]["file_name"] == "sample.pdf"
    assert data["document"]["questions"][0]["source_question_id"] == "1"
    assert data["issues"][0]["issue_code"] == "X"


def test_export_preserves_math_symbols(tmp_path):
    document = ExtractedDocument(
        file_name="sample.pdf",
        page_count=1,
        questions=[
            ExtractedQuestion(
                source_question_id="1",
                page_start=1,
                page_end=1,
                question_text="1 − 225x²",
            )
        ],
    )

    output_path = tmp_path / "sample.pdf.json"
    export_extraction_json(document, [], output_path)

    raw = output_path.read_text(encoding="utf-8")
    assert "1 − 225x²" in raw
