import json

from app.json_exporter import export_extraction_json, extraction_output_path
from app.schemas import ValidationIssue


def test_export_includes_source_run_document_and_issues(tmp_path, make_result):
    result = make_result(issues=[
        ValidationIssue(issue_code="X", severity="low", message="note", source_question_id="1"),
    ])
    path = export_extraction_json(result, tmp_path / "nested" / "out.json")

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["document"]["file_name"] == "sample.pdf"
    assert data["document"]["questions"][0]["source_question_id"] == "1"
    assert data["source"]["sha256"] == "a" * 64
    assert data["source"]["byte_size"] == 1234
    assert data["run"]["extraction_version"] == "QEE_v1"
    assert data["run"]["question_object_version"] == "QOS_v1"
    assert data["run"]["model"] == "test-model"
    assert data["issues"][0]["issue_code"] == "X"
    assert data["issues"][0]["source_question_id"] == "1"


def test_export_is_json_serialisable_end_to_end(tmp_path, make_result):
    # Guards against a non-JSON type (e.g. datetime) creeping into a model.
    path = export_extraction_json(make_result(), tmp_path / "out.json")
    json.loads(path.read_text(encoding="utf-8"))


def test_export_preserves_math_symbols(tmp_path, make_result, make_document, make_question):
    document = make_document([make_question(question_text="1 − 225x² ÷ ½π")])
    path = export_extraction_json(make_result(document=document), tmp_path / "out.json")
    assert "1 − 225x² ÷ ½π" in path.read_text(encoding="utf-8")


def test_output_path_is_named_by_content_hash(make_result):
    path = extraction_output_path(make_result(sha256="abcdef1234567890" + "0" * 48))
    assert path.name == "sample-abcdef123456.json"


def test_same_name_different_content_does_not_collide(make_result):
    a = extraction_output_path(make_result(sha256="a" * 64))
    b = extraction_output_path(make_result(sha256="b" * 64))
    assert a != b


def test_same_content_reuses_the_same_path(make_result):
    a = extraction_output_path(make_result(sha256="c" * 64))
    b = extraction_output_path(make_result(sha256="c" * 64))
    assert a == b
