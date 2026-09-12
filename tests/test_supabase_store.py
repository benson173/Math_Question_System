"""Writing an extraction to Supabase, against a fake client."""

from __future__ import annotations

import pytest

from app.repository import Repository
from app.supabase_store import (
    SaveOutcome,
    StoreError,
    SupabaseStore,
    document_row,
    question_rows,
    run_row,
)
from app.schemas import (
    ExtractedDocument,
    ExtractedQuestion,
    ExtractionResult,
    ExtractionRun,
    PageRegion,
    RenderedImage,
    SourceDocument,
    ValidationIssue,
)


# --- a fake client with the chainable API supabase-py exposes ---------------

class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, client, table):
        self.client, self.table_name = client, table
        self.op, self.payload, self.filters = None, None, []

    def upsert(self, row, on_conflict=None):
        self.op, self.payload = "upsert", row
        return self

    def insert(self, rows):
        self.op, self.payload = "insert", rows
        return self

    def update(self, values):
        self.op, self.payload = "update", values
        return self

    def delete(self):
        self.op = "delete"
        return self

    def eq(self, column, value):
        self.filters.append(("eq", column, value))
        return self

    def neq(self, column, value):
        self.filters.append(("neq", column, value))
        return self

    def execute(self):
        return self.client.run(self)


class FakeClient:
    def __init__(self, fail_on=None):
        self.calls = []
        self.rows = {"source_documents": [], "extraction_runs": [], "questions": []}
        self.fail_on = fail_on
        self._next = 1

    def table(self, name):
        return FakeQuery(self, name)

    def _id(self):
        self._next += 1
        return f"id-{self._next - 1}"

    def run(self, query):
        self.calls.append((query.table_name, query.op, query.payload, list(query.filters)))
        if self.fail_on == (query.table_name, query.op):
            raise RuntimeError(f"simulated failure on {query.table_name}.{query.op}")

        store = self.rows[query.table_name]
        if query.op == "upsert":
            existing = next((r for r in store if r["sha256"] == query.payload["sha256"]), None)
            if existing:
                existing.update(query.payload)
                return FakeResponse([existing])
            row = {"id": self._id(), **query.payload}
            store.append(row)
            return FakeResponse([row])
        if query.op == "insert":
            rows = query.payload if isinstance(query.payload, list) else [query.payload]
            written = [{"id": self._id(), **r} for r in rows]
            store.extend(written)
            return FakeResponse(written)
        if query.op == "update":
            hit = [r for r in store if all(self._match(r, f) for f in query.filters)]
            for r in hit:
                r.update(query.payload)
            return FakeResponse(hit)
        if query.op == "delete":
            hit = [r for r in store if all(self._match(r, f) for f in query.filters)]
            for r in hit:
                store.remove(r)
            return FakeResponse(hit)
        raise AssertionError(query.op)

    @staticmethod
    def _match(row, f):
        kind, column, value = f
        return row.get(column) == value if kind == "eq" else row.get(column) != value


# --- fixtures ---------------------------------------------------------------

def make_result(questions=None, issues=None, sha="a" * 64, run_id="run1") -> ExtractionResult:
    questions = questions if questions is not None else [
        ExtractedQuestion(source_question_id="1", page_start=1, page_end=1,
                          question_text="求 x。", marks=3),
        ExtractedQuestion(source_question_id="2(a)", page_start=2, page_end=2,
                          question_text="因式分解。", group_marks=4, group_marks_scope="2",
                          question_type="multiple_choice", options=["a", "b"],
                          diagram_required=True,
                          diagram_region=PageRegion(page=2, y_min=1, x_min=1, y_max=9, x_max=9),
                          extraction_notes=["note"]),
    ]
    document = ExtractedDocument(file_name="p.pdf", page_count=3, questions=questions)
    return ExtractionResult(
        document=document,
        issues=issues or [],
        source=SourceDocument(file_name="p.pdf", sha256=sha, page_count=3, byte_size=100),
        run=ExtractionRun(run_id=run_id, extracted_at="2026-09-12T00:00:00+00:00",
                          extraction_version="QEE_v1", question_object_version="QOS_v1",
                          model="m"),
        diagrams=[RenderedImage(source_question_id="2(a)", kind="diagram", index=0, page=2,
                                image_path="data/diagrams/p-aaaa/2-a.png", cropped=True,
                                width=10, height=10)],
        repairs=["19: removed 'x'"],
    )


# --- row builders -----------------------------------------------------------

def test_document_row_carries_the_hash():
    row = document_row(make_result())
    assert row == {"sha256": "a" * 64, "file_name": "p.pdf", "page_count": 3, "byte_size": 100}


def test_document_row_needs_a_source():
    result = make_result()
    result.source = None
    with pytest.raises(StoreError):
        document_row(result)


def test_run_row_summarises_the_run():
    result = make_result(issues=[ValidationIssue(issue_code="NO_QUESTIONS_FOUND",
                                                  severity="critical", message="m")])
    row = run_row(result, "doc-1")
    assert row["run_id"] == "run1"
    assert row["source_document_id"] == "doc-1"
    assert row["question_count"] == 2
    assert row["issue_count"] == 1
    assert row["blocking"] is True
    assert row["issues"][0]["issue_code"] == "NO_QUESTIONS_FOUND"
    assert row["repairs"] == ["19: removed 'x'"]
    assert row["is_current"] is True


def test_question_rows_keep_order_and_every_field():
    rows = question_rows(make_result(), "doc-1", "run-1")
    assert [r["position"] for r in rows] == [1, 2]
    assert [r["source_question_id"] for r in rows] == ["1", "2(a)"]

    first, second = rows
    assert first["marks"] == 3 and first["question_type"] == "open"
    assert second["question_type"] == "multiple_choice"
    assert second["options"] == ["a", "b"]
    assert second["group_marks"] == 4 and second["group_marks_scope"] == "2"
    assert second["diagram_region"]["page"] == 2
    assert second["extraction_notes"] == ["note"]
    assert all(r["extraction_run_id"] == "run-1" for r in rows)


def test_rendered_images_are_attached_to_their_question():
    rows = question_rows(make_result(), "doc-1", "run-1")
    assert rows[0]["images"] == []
    assert rows[1]["images"][0]["kind"] == "diagram"
    assert rows[1]["images"][0]["image_path"].endswith("2-a.png")


def test_row_values_are_json_serialisable():
    import json
    result = make_result()
    json.dumps(document_row(result))
    json.dumps(run_row(result, "d"))
    json.dumps(question_rows(result, "d", "r"))


# --- the store --------------------------------------------------------------

def test_save_writes_all_three_tables():
    client = FakeClient()
    outcome = SupabaseStore(client).save(make_result())

    assert isinstance(outcome, SaveOutcome)
    assert outcome.questions == 2
    assert len(client.rows["source_documents"]) == 1
    assert len(client.rows["extraction_runs"]) == 1
    assert len(client.rows["questions"]) == 2
    assert client.rows["questions"][0]["source_document_id"] == outcome.document_id
    assert client.rows["questions"][0]["extraction_run_id"] == outcome.run_id


def test_the_same_pdf_is_one_document():
    client = FakeClient()
    store = SupabaseStore(client)
    first = store.save(make_result(run_id="run1"))
    second = store.save(make_result(run_id="run2"))

    assert first.document_id == second.document_id
    assert len(client.rows["source_documents"]) == 1
    assert len(client.rows["extraction_runs"]) == 2


def test_a_new_run_supersedes_the_old_one():
    client = FakeClient()
    store = SupabaseStore(client)
    store.save(make_result(run_id="run1"))
    outcome = store.save(make_result(run_id="run2"))

    assert outcome.superseded_runs == 1
    current = [r for r in client.rows["extraction_runs"] if r["is_current"]]
    assert [r["run_id"] for r in current] == ["run2"]


def test_a_failed_question_insert_removes_the_run():
    client = FakeClient(fail_on=("questions", "insert"))
    with pytest.raises(RuntimeError):
        SupabaseStore(client).save(make_result())

    assert client.rows["extraction_runs"] == []
    assert len(client.rows["source_documents"]) == 1      # the document is still fine


def test_upsert_conflicts_on_the_hash():
    client = FakeClient()
    SupabaseStore(client).save(make_result())
    table, op, payload, _ = client.calls[0]
    assert (table, op) == ("source_documents", "upsert")


# --- through the repository -------------------------------------------------

def test_repository_without_a_store_only_prints(capsys):
    repo = Repository(verbose=False, store=None)
    assert repo.writes_to_database is False
    assert repo.save_extraction_result(make_result()) is None


def test_repository_with_a_store_writes_and_reports(capsys):
    client = FakeClient()
    repo = Repository(verbose=False, store=SupabaseStore(client))
    outcome = repo.save_extraction_result(make_result())

    assert outcome.questions == 2
    assert "Supabase:" in capsys.readouterr().out
    assert len(client.rows["questions"]) == 2
