"""Filling the database from extractions already on disk."""

from __future__ import annotations

import json

import pytest

from app.json_exporter import export_extraction_json
from app.schemas import ExtractionResult
from scripts import db_push
from tests.test_supabase_store import FakeClient, make_result


class Settings:
    supabase_url = "https://x.supabase.co"
    supabase_secret_key = "service-role-key"


def write_extraction(directory, name="p.pdf", run_id="run1", sha="a" * 64):
    result = make_result(run_id=run_id, sha=sha)
    result.document.file_name = name
    result.source.file_name = name
    path = directory / f"{name}-{run_id}.json"
    return export_extraction_json(result, path)


@pytest.fixture
def wired(monkeypatch):
    """db_push with a fake client and settings, and no real connection."""
    client = FakeClient()
    monkeypatch.setattr(db_push, "load_settings", lambda: Settings())
    monkeypatch.setattr(db_push, "connect", lambda url, key: client)
    return client


# --- reading the files ------------------------------------------------------

def test_the_json_a_run_writes_can_be_read_back(tmp_path):
    path = write_extraction(tmp_path)
    result = ExtractionResult.model_validate(json.loads(path.read_text(encoding="utf-8")))
    assert result.document.file_name == "p.pdf"
    assert len(result.document.questions) == 2
    assert result.run.run_id == "run1"
    assert result.diagrams[0].source_question_id == "2(a)"


def test_the_archive_keeps_table_images_and_repairs(tmp_path):
    # Both were missing from the export, which made a pushed run lossy.
    data = json.loads(write_extraction(tmp_path).read_text(encoding="utf-8"))
    assert "tables" in data and "repairs" in data
    assert data["repairs"] == ["19: removed 'x'"]


def test_a_file_that_is_not_an_extraction_is_skipped(tmp_path, capsys):
    (tmp_path / "batch-report.json").write_text('{"summary": "not an extraction"}')
    assert db_push.load_results([tmp_path / "batch-report.json"]) == []
    assert "skipped" in capsys.readouterr().out


# --- pushing ----------------------------------------------------------------

def test_every_paper_in_the_folder_is_pushed(tmp_path, wired, capsys):
    write_extraction(tmp_path, name="a.pdf", run_id="run-a", sha="a" * 64)
    write_extraction(tmp_path, name="b.pdf", run_id="run-b", sha="b" * 64)

    assert db_push.main([str(p) for p in sorted(tmp_path.glob("*.json"))]) == 0
    assert len(wired.rows["source_documents"]) == 2
    assert len(wired.rows["extraction_runs"]) == 2
    assert len(wired.rows["questions"]) == 4
    assert "2 pushed (4 questions)" in capsys.readouterr().out


def test_a_run_already_in_the_database_is_not_pushed_twice(tmp_path, wired, capsys):
    path = write_extraction(tmp_path, run_id="run-a")
    assert db_push.main([str(path)]) == 0
    assert db_push.main([str(path)]) == 0

    assert len(wired.rows["extraction_runs"]) == 1
    assert len(wired.rows["questions"]) == 2
    assert "already" in capsys.readouterr().out


def test_force_replaces_a_run_that_is_already_there(tmp_path, wired):
    path = write_extraction(tmp_path, run_id="run-a")
    db_push.main([str(path)])
    assert db_push.main([str(path), "--force"]) == 0
    # run_id is unique in the database, so --force replaces rather than doubles
    assert [r["run_id"] for r in wired.rows["extraction_runs"]] == ["run-a"]
    assert len(wired.rows["questions"]) == 2


def test_a_write_that_fails_is_reported_and_the_rest_continue(tmp_path, monkeypatch, capsys):
    client = FakeClient()
    monkeypatch.setattr(db_push, "load_settings", lambda: Settings())
    monkeypatch.setattr(db_push, "connect", lambda url, key: client)

    write_extraction(tmp_path, name="a.pdf", run_id="run-a", sha="a" * 64)
    write_extraction(tmp_path, name="b.pdf", run_id="run-b", sha="b" * 64)

    real_save = db_push.SupabaseStore.save
    def save(self, result):
        if result.document.file_name == "a.pdf":
            raise RuntimeError("column questions.level does not exist")
        return real_save(self, result)
    monkeypatch.setattr(db_push.SupabaseStore, "save", save)

    assert db_push.main([str(p) for p in sorted(tmp_path.glob("*.json"))]) == 1
    printed = capsys.readouterr().out
    assert "FAILED" in printed and "a.pdf" in printed
    assert "1 pushed" in printed and "1 failed" in printed
    assert "scripts.db_check" in printed          # points at the usual cause


def test_without_env_it_says_so_and_writes_nothing(tmp_path, monkeypatch, capsys):
    class Unset:
        supabase_url = ""
        supabase_secret_key = ""
    monkeypatch.setattr(db_push, "load_settings", lambda: Unset())
    assert db_push.main([str(write_extraction(tmp_path))]) == 2
    assert "not set in .env" in capsys.readouterr().out


def test_an_empty_folder_is_not_an_error(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(db_push, "load_settings", lambda: Settings())
    monkeypatch.setattr(db_push, "EXTRACTED_DIR", tmp_path / "empty")
    assert db_push.main([]) == 0
    assert "No extraction JSON found" in capsys.readouterr().out


# --- what the scripts say about where data goes -----------------------------

def test_the_repository_says_when_nothing_reaches_the_database():
    from app.repository import Repository
    repo = Repository(verbose=False, store=None)
    assert "JSON files only" in repo.describe_target()
    assert "SUPABASE_URL" in repo.describe_target()


def test_the_repository_names_the_project_it_writes_to():
    from app.repository import Repository
    from app.supabase_store import SupabaseStore
    repo = Repository(verbose=False, store=SupabaseStore(FakeClient()))
    assert "Supabase at" in repo.describe_target()


# --- old files, written before the level existed -----------------------------

def test_an_old_extraction_gets_its_form_from_the_file_name(tmp_path, wired, capsys):
    result = make_result(run_id="run-old")
    result.document.file_name = "S5-2024-mock.pdf"
    result.source.file_name = "S5-2024-mock.pdf"
    result.document.level = None
    result.document.level_source = None
    export_extraction_json(result, tmp_path / "old.json")

    assert db_push.main([str(tmp_path / "old.json")]) == 0
    assert wired.rows["source_documents"][0]["level"] == "F5"
    assert all(row["level"] == "F5" for row in wired.rows["questions"])
    assert "read F5 off the file name" in capsys.readouterr().out


def test_a_file_name_with_no_form_stays_null(tmp_path, wired):
    result = make_result(run_id="run-x")
    result.document.file_name = "mock-paper.pdf"
    result.document.level = None
    result.document.level_source = None
    export_extraction_json(result, tmp_path / "x.json")

    assert db_push.main([str(tmp_path / "x.json")]) == 0
    assert wired.rows["source_documents"][0].get("level") is None


def test_an_old_extraction_gets_its_paper_context_from_the_file_name(tmp_path, wired):
    result = make_result(run_id="run-meta")
    result.document.file_name = "2526_1st_S4MATH1.pdf"
    result.document.paper = None
    export_extraction_json(result, tmp_path / "meta.json")

    assert db_push.main([str(tmp_path / "meta.json")]) == 0
    doc = wired.rows["source_documents"][0]
    assert (doc["year"], doc["term"], doc["paper_number"]) == ("2025-26", "1st", 1)


def test_an_old_extraction_gets_its_module_from_the_file_name(tmp_path, wired, capsys):
    result = make_result(run_id="run-mod")
    result.document.file_name = "2024-dse-m1-paper1.pdf"
    result.document.module = None
    export_extraction_json(result, tmp_path / "m.json")

    assert db_push.main([str(tmp_path / "m.json")]) == 0
    assert wired.rows["source_documents"][0]["module"] == "M1"
    assert all(row["module"] == "M1" for row in wired.rows["questions"])
    assert "module   2024-dse-m1-paper1.pdf  M1" in capsys.readouterr().out
