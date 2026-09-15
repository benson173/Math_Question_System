"""Write an extraction into Supabase.

Two halves, kept apart on purpose. The row builders are pure functions from an
ExtractionResult to plain dicts, so the exact shape written can be tested
without a database; SupabaseStore is the thin part that hands those rows to a
client. If your tables use different column names, the builders are the one
place to change.

One extraction becomes:
    1 source_documents row   (upserted on sha256 - the same PDF is one document;
                              carries the form, F1-F6)
    1 extraction_runs row    (every run is kept; the newest is is_current)
    N questions rows         (one per question, tied to that run)

Supabase's REST API has no transactions, so if the questions fail to insert the
run row is deleted again rather than left as an empty run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.extraction_validator import blocking_issues
from app.question_key import question_key
from app.schemas import ExtractionResult, RenderedImage


TABLE_DOCUMENTS = "source_documents"
TABLE_RUNS = "extraction_runs"
TABLE_QUESTIONS = "questions"


class StoreError(RuntimeError):
    """The database refused or returned nothing usable."""


@dataclass
class SaveOutcome:
    document_id: str
    run_id: str
    questions: int
    superseded_runs: int


# --- rows -----------------------------------------------------------------

def document_row(result: ExtractionResult) -> dict[str, Any]:
    if result.source is None:
        raise StoreError("Cannot save an extraction with no source document (sha256).")
    row = {
        "sha256": result.source.sha256,
        "file_name": result.source.file_name,
        "page_count": result.source.page_count,
        "byte_size": result.source.byte_size,
        **_paper_columns(result),
    }
    # Only a known form is written: an upsert with level null would wipe the
    # form a previous run of the same paper had established.
    if result.document.level:
        row["level"] = result.document.level
    if result.document.module:
        row["module"] = result.document.module
    return row


def _paper_columns(result: ExtractionResult) -> dict[str, Any]:
    paper = result.document.paper
    if paper is None:
        return {}
    return {
        "year": paper.year,
        "term": paper.term,
        "exam_type": paper.exam_type,
        "paper_number": paper.paper_number,
        "school": paper.school,
        "topics": list(paper.topics),
    }


def run_row(result: ExtractionResult, document_id: str) -> dict[str, Any]:
    if result.run is None:
        raise StoreError("Cannot save an extraction with no run metadata.")
    return {
        "run_id": result.run.run_id,
        "source_document_id": document_id,
        "extracted_at": result.run.extracted_at,
        "extraction_version": result.run.extraction_version,
        "question_object_version": result.run.question_object_version,
        "model": result.run.model,
        "prompt_sha256": result.run.prompt_sha256,
        "input_tokens": result.run.input_tokens,
        "output_tokens": result.run.output_tokens,
        "question_count": len(result.document.questions),
        "issue_count": len(result.issues),
        "blocking": bool(blocking_issues(result.issues)),
        "issues": [issue.model_dump() for issue in result.issues],
        "repairs": list(result.repairs),
        "marking_scheme_file_name": result.document.marking_scheme.file_name
                                    if result.document.marking_scheme else None,
        "marking_scheme_sha256": result.document.marking_scheme.sha256
                                 if result.document.marking_scheme else None,
        # A run with a blocking issue is kept for the record but never becomes
        # the paper's current questions: a re-extraction that came back empty
        # must not hide the good run before it.
        "is_current": not bool(blocking_issues(result.issues)),
    }


def _images_by_question(result: ExtractionResult) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for asset in list(result.diagrams) + list(result.tables):
        grouped.setdefault(asset.source_question_id, []).append(_image_row(asset))
    return grouped


def _image_row(asset: RenderedImage) -> dict[str, Any]:
    return {
        "kind": asset.kind,
        "index": asset.index,
        "page": asset.page,
        "image_path": asset.image_path,
        "cropped": asset.cropped,
        "width": asset.width,
        "height": asset.height,
    }


def _answer_source(question, document) -> str | None:
    scheme = document.marking_scheme
    if scheme and question.source_question_id in scheme.matched:
        return "marking_scheme"
    if question.answer or question.worked_solution:
        return "paper"
    return None


def question_rows(result: ExtractionResult, document_id: str, run_id: str) -> list[dict[str, Any]]:
    images = _images_by_question(result)
    rows = []
    for position, q in enumerate(result.document.questions, start=1):
        rows.append({
            "extraction_run_id": run_id,
            "source_document_id": document_id,
            "source_question_id": q.source_question_id,
            "question_key": question_key(result.source.sha256, q.source_question_id)
                            if result.source and q.source_question_id.strip() else None,
            "depends_on": list(q.depends_on),
            "level": result.document.level,
            "module": result.document.module,
            "position": position,
            "question_type": q.question_type,
            "question_text": q.question_text,
            "options": list(q.options),
            "marks": q.marks,
            "group_marks": q.group_marks,
            "group_marks_scope": q.group_marks_scope,
            "answer": q.answer,
            "answer_source": _answer_source(q, result.document),
            "worked_solution": q.worked_solution,
            "page_start": q.page_start,
            "page_end": q.page_end,
            "diagram_required": q.diagram_required,
            "diagram_region": q.diagram_region.model_dump() if q.diagram_region else None,
            "table_regions": [r.model_dump() for r in q.table_regions],
            "extraction_notes": list(q.extraction_notes),
            "images": images.get(q.source_question_id, []),
        })
    return rows


# --- the store ------------------------------------------------------------

def _first_id(response: Any, what: str) -> str:
    data = getattr(response, "data", None) or []
    if not data or "id" not in data[0]:
        raise StoreError(f"Supabase returned no id after writing {what}.")
    return str(data[0]["id"])


class SupabaseStore:
    def __init__(self, client: Any):
        self.client = client

    def save(self, result: ExtractionResult) -> SaveOutcome:
        document_id = self._upsert_document(result)
        run_id = self._insert_run(result, document_id)
        try:
            count = self._insert_questions(result, document_id, run_id)
            superseded = (self._supersede_older_runs(document_id, run_id)
                          if not blocking_issues(result.issues) else 0)
        except Exception:
            # No transactions over REST: do not leave a half-written run, and
            # not its questions either - the migrated schema has no cascade.
            self._delete_run_rows(run_id)
            raise
        return SaveOutcome(document_id, run_id, count, superseded)

    def delete_run(self, run_id: str) -> bool:
        """Remove a run and its questions by the pipeline's run_id, if present."""
        response = (self.client.table(TABLE_RUNS).select("id")
                    .eq("run_id", run_id).limit(1).execute())
        rows = getattr(response, "data", None) or []
        if not rows:
            return False
        self._delete_run_rows(str(rows[0]["id"]))
        return True

    def _delete_run_rows(self, run_row_id: str) -> None:
        self.client.table(TABLE_QUESTIONS).delete().eq("extraction_run_id", run_row_id).execute()
        self.client.table(TABLE_RUNS).delete().eq("id", run_row_id).execute()

    def _upsert_document(self, result: ExtractionResult) -> str:
        response = (self.client.table(TABLE_DOCUMENTS)
                    .upsert(document_row(result), on_conflict="sha256")
                    .execute())
        return _first_id(response, "source_documents")

    def _insert_run(self, result: ExtractionResult, document_id: str) -> str:
        response = self.client.table(TABLE_RUNS).insert(run_row(result, document_id)).execute()
        return _first_id(response, "extraction_runs")

    def _insert_questions(self, result: ExtractionResult, document_id: str, run_id: str) -> int:
        rows = question_rows(result, document_id, run_id)
        if not rows:
            return 0
        self.client.table(TABLE_QUESTIONS).insert(rows).execute()
        return len(rows)

    def _supersede_older_runs(self, document_id: str, run_id: str) -> int:
        response = (self.client.table(TABLE_RUNS)
                    .update({"is_current": False})
                    .eq("source_document_id", document_id)
                    .neq("id", run_id)
                    .eq("is_current", True)
                    .execute())
        return len(getattr(response, "data", None) or [])


def key_warning(key: str) -> str | None:
    """Why this key will not be able to write, if it will not.

    Tables made in the Supabase UI have row-level security on with no
    policies, so an anon or publishable key reads nothing and writes nothing -
    without an error. Only the service_role (secret) key bypasses that.
    """
    if not key:
        return None
    if key.startswith("sb_publishable_"):
        return ("SUPABASE_SECRET_KEY is a publishable key. Use the secret "
                "(service_role) key: writes with this one are refused by row-level "
                "security, silently.")
    if key.startswith("sb_secret_"):
        return None
    parts = key.split(".")
    if len(parts) == 3:                              # a JWT: read its role claim
        import base64
        import json
        try:
            payload = parts[1] + "=" * (-len(parts[1]) % 4)
            role = json.loads(base64.urlsafe_b64decode(payload)).get("role")
        except Exception:
            return None
        if role and role != "service_role":
            return (f"SUPABASE_SECRET_KEY is the {role!r} key. Use the service_role key: "
                    f"writes with this one are refused by row-level security, silently.")
    return None


def connect(url: str, key: str) -> Any:
    """Build a Supabase client, failing with a plain message if the SDK is absent."""
    try:
        from supabase import create_client
    except ImportError as exc:
        raise StoreError("The supabase package is not installed: pip install supabase") from exc
    return create_client(url, key)
