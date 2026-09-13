"""The ingestion faults found in the whole-system review, each pinned down."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.gemini_client import prompt_sha256, usage_from
from app.markdown_exporter import _relative_link
from app.paths import PROJECT_ROOT, project_absolute, project_relative
from app.pipeline import PdfIngestionPipeline
from app.schemas import ValidationIssue
from app.supabase_store import SupabaseStore, document_row, key_warning, run_row
from scripts import db_push
from scripts import ingest_one_pdf as single
from scripts import ingest_pdfs as batch
from tests.test_marking_scheme import FakeExtractor, Settings
from tests.test_supabase_store import FakeClient, make_result


# --- A1: the JSON is written before the database is touched -----------------

class ExplodingRepository:
    def save_extraction_result(self, result):
        raise ConnectionError("Supabase is down")


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr("app.json_exporter.EXTRACTED_DIR", tmp_path / "extracted")
    monkeypatch.setattr("app.json_exporter.HISTORY_DIR", tmp_path / "history")
    monkeypatch.setattr("app.json_exporter.DIAGRAMS_DIR", tmp_path / "diagrams")
    return tmp_path


def test_a_database_failure_does_not_lose_the_extraction(isolated, capsys):
    pipeline = PdfIngestionPipeline(extractor=FakeExtractor(make_result()),
                                    repository=ExplodingRepository(), settings=Settings())
    result = pipeline.run_one_pdf("p.pdf")

    written = list((isolated / "extracted").glob("*.json"))
    assert len(written) == 1                                  # the API call is banked
    assert result.database_error == "ConnectionError: Supabase is down"
    printed = capsys.readouterr().out
    assert "not saved to the database" in printed and "db_push" in printed


def test_a_database_failure_is_not_a_failed_paper(isolated, monkeypatch, tmp_path, capsys):
    from tests.test_batch_ingest import inbox as _inbox  # noqa: F401
    paths = {name: tmp_path / name for name in ("inbox", "processed", "failed")}
    for p in paths.values():
        p.mkdir()
    monkeypatch.setattr(batch, "INBOX_PDF_DIR", paths["inbox"])
    monkeypatch.setattr(batch, "PROCESSED_PDF_DIR", paths["processed"])
    monkeypatch.setattr(batch, "FAILED_PDF_DIR", paths["failed"])
    monkeypatch.setattr(batch, "EXTRACTED_DIR", isolated / "extracted")

    class FakePipeline:
        def __init__(self, *a, **k):
            pass

        def run_one_pdf(self, path, marking_scheme_path=None):
            result = make_result()
            result.document.file_name = path.name
            result.database_error = "APIError: nope"
            return result

    class FakeRepository:
        def __init__(self, verbose=True): pass
        def describe_target(self): return "test"

    monkeypatch.setattr(batch, "PdfIngestionPipeline", FakePipeline)
    monkeypatch.setattr(batch, "Repository", FakeRepository)
    (paths["inbox"] / "a.pdf").write_bytes(b"AAA")

    assert batch.main([]) == 0                                # ok, with a note
    assert (paths["processed"] / "a.pdf").exists()            # not filed as failed
    assert "not saved to database" in capsys.readouterr().out


# --- A2: a blocking run never becomes the current one -----------------------

def blocking(result):
    result.issues = [ValidationIssue(issue_code="NO_QUESTIONS_FOUND", severity="critical",
                                     message="m")]
    result.document.questions = []
    return result


def test_a_blocking_run_is_stored_but_not_current():
    client = FakeClient()
    store = SupabaseStore(client)
    store.save(make_result(run_id="good"))
    outcome = store.save(blocking(make_result(run_id="bad")))

    runs = {r["run_id"]: r["is_current"] for r in client.rows["extraction_runs"]}
    assert runs == {"good": True, "bad": False}
    assert outcome.superseded_runs == 0


def test_run_row_says_so_up_front():
    assert run_row(blocking(make_result()), "d")["is_current"] is False
    assert run_row(make_result(), "d")["is_current"] is True


# --- A5: a failed save leaves no orphan questions ---------------------------

def test_a_failed_supersede_removes_the_questions_as_well():
    client = FakeClient(fail_on=("extraction_runs", "update"))
    store = SupabaseStore(client)
    store.rows = None
    with pytest.raises(RuntimeError):
        store.save(make_result())
    assert client.rows["extraction_runs"] == []
    assert client.rows["questions"] == []


# --- A4: --force replaces a run instead of colliding with it ---------------

class Env:
    supabase_url = "https://x.supabase.co"
    supabase_secret_key = "sb_secret_abc"


def test_force_replaces_the_run_rather_than_duplicating_it(tmp_path, monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(db_push, "load_settings", lambda: Env())
    monkeypatch.setattr(db_push, "connect", lambda url, key: client)
    from app.json_exporter import export_extraction_json
    path = export_extraction_json(make_result(run_id="run-a"), tmp_path / "a.json")

    assert db_push.main([str(path)]) == 0
    assert db_push.main([str(path), "--force"]) == 0          # would raise on the old code
    assert [r["run_id"] for r in client.rows["extraction_runs"]] == ["run-a"]
    assert len(client.rows["questions"]) == 2                 # replaced, not doubled


def test_the_fake_client_really_enforces_run_id_uniqueness():
    store = SupabaseStore(FakeClient())
    store.save(make_result(run_id="dup"))
    with pytest.raises(RuntimeError):
        store.save(make_result(run_id="dup"))


# --- B6: the wrong kind of key is named before it fails silently ------------

def jwt(role):
    import base64
    payload = base64.urlsafe_b64encode(json.dumps({"role": role}).encode()).decode().rstrip("=")
    return f"eyJhbGciOiJIUzI1NiJ9.{payload}.sig"


@pytest.mark.parametrize("key,expected", [
    ("sb_publishable_abc", "publishable"),
    (jwt("anon"), "'anon'"),
    (jwt("service_role"), None),
    ("sb_secret_abc", None),
    ("", None),
    ("not-a-jwt-at-all", None),
])
def test_key_warning(key, expected):
    warning = key_warning(key)
    if expected is None:
        assert warning is None
    else:
        assert expected in warning and "service_role" in warning


# --- B7: image paths are stored relative to the project -------------------

def test_a_path_inside_the_project_is_stored_relative():
    stored = project_relative(PROJECT_ROOT / "data" / "diagrams" / "p-abc" / "16.png")
    assert stored == "data/diagrams/p-abc/16.png"
    assert project_absolute(stored) == PROJECT_ROOT / "data/diagrams/p-abc/16.png"


def test_a_path_outside_the_project_stays_absolute(tmp_path):
    outside = tmp_path / "16.png"
    assert project_relative(outside) == str(outside.resolve())


def test_the_report_links_a_relative_image_from_the_project_root():
    report = PROJECT_ROOT / "data" / "extracted" / "p-abc.md"
    link = _relative_link("data/diagrams/p-abc/16.png", report)
    assert link == "../diagrams/p-abc/16.png"


# --- B8: ingest_one_pdf files an inbox PDF away like the batch does ---------

def test_an_inbox_pdf_is_moved_after_ingestion(tmp_path, monkeypatch, capsys):
    paths = {name: tmp_path / name for name in ("inbox", "processed", "failed")}
    for p in paths.values():
        p.mkdir()
    monkeypatch.setattr(single, "INBOX_PDF_DIR", paths["inbox"])
    monkeypatch.setattr(batch, "PROCESSED_PDF_DIR", paths["processed"])
    monkeypatch.setattr(batch, "FAILED_PDF_DIR", paths["failed"])

    class FakePipeline:
        def __init__(self, *a, **k): pass
        def run_one_pdf(self, path): return make_result()

    class FakeRepository:
        def __init__(self, *a, **k): pass
        def describe_target(self): return "test"

    monkeypatch.setattr(single, "PdfIngestionPipeline", FakePipeline)
    monkeypatch.setattr(single, "Repository", FakeRepository)
    pdf = paths["inbox"] / "sample.pdf"
    pdf.write_bytes(b"%PDF")

    assert single.main([str(pdf)]) == 0
    assert (paths["processed"] / "sample.pdf").exists() and not pdf.exists()
    assert "Moved to" in capsys.readouterr().out


def test_a_pdf_named_from_elsewhere_stays_put(tmp_path, monkeypatch):
    monkeypatch.setattr(single, "INBOX_PDF_DIR", tmp_path / "inbox")
    elsewhere = tmp_path / "desk" / "paper.pdf"
    elsewhere.parent.mkdir()
    elsewhere.write_bytes(b"%PDF")
    assert single.file_away_if_in_inbox(elsewhere, make_result()) is None
    assert elsewhere.exists()


# --- B10: an unknown form does not overwrite a known one --------------------

def test_level_is_left_out_of_the_row_when_unknown():
    result = make_result()
    result.document.level = None
    assert "level" not in document_row(result)
    assert document_row(make_result())["level"] == "F4"


# --- C11 / C12: the run records its prompt and its cost ---------------------

class Usage:
    prompt_token_count = 1200
    candidates_token_count = 340


class Response:
    usage_metadata = Usage()


def test_usage_is_read_off_the_response():
    assert usage_from(Response()) == {"input_tokens": 1200, "output_tokens": 340}
    assert usage_from(object()) == {"input_tokens": None, "output_tokens": None}


def test_the_prompt_hash_changes_when_the_prompt_does(tmp_path):
    prompt = tmp_path / "p.txt"
    prompt.write_text("ROLE\nclerk\n")
    before = prompt_sha256(prompt)
    prompt.write_text("ROLE\nclerk\n\nDO\n- more\n")
    assert len(before) == 12 and before != prompt_sha256(prompt)


def test_the_run_record_carries_prompt_and_tokens():
    from app.document_extractor import DocumentExtractor

    class Gem:
        last_usage = {"input_tokens": 10, "output_tokens": 5}

    class Cfg:
        extraction_version = "QEE_v1"
        question_object_version = "QOS_v1"
        gemini_extractor_model = "m"

    extractor = DocumentExtractor.__new__(DocumentExtractor)
    extractor.gemini, extractor.settings = Gem(), Cfg()
    run = extractor._describe_run()
    assert (run.input_tokens, run.output_tokens) == (10, 5)
    assert len(run.prompt_sha256) == 12


def test_the_run_row_and_report_carry_them():
    from app.markdown_exporter import render_markdown
    result = make_result()
    result.run.prompt_sha256, result.run.input_tokens, result.run.output_tokens = "abc123abc123", 1200, 340
    row = run_row(result, "d")
    assert (row["prompt_sha256"], row["input_tokens"], row["output_tokens"]) == ("abc123abc123", 1200, 340)
    text = render_markdown(result, Path("/tmp/r.md"))
    assert "`abc123abc123`" in text and "1,200 in / 340 out" in text


# --- C14: one loader --------------------------------------------------------

def test_every_script_reads_json_through_the_same_loader(tmp_path):
    from app.extraction_io import load_extraction, load_extractions
    from app.json_exporter import export_extraction_json
    good = export_extraction_json(make_result(), tmp_path / "good.json")
    (tmp_path / "batch.json").write_text('{"summary": 1}')
    skipped = []
    loaded = load_extractions([good, tmp_path / "batch.json"],
                              on_skip=lambda p, e: skipped.append(p.name))
    assert [p.name for p, _ in loaded] == ["good.json"]
    assert skipped == ["batch.json"]
    assert load_extraction(good).document.file_name == "p.pdf"
