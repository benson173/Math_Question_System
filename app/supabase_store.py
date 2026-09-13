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
    return {
        "sha256": result.source.sha256,
        "file_name": result.source.file_name,
        "page_count": result.source.page_count,
        "byte_size": result.source.byte_size,
        "level": result.document.level,
        **_paper_columns(result),
    }


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
        "question_count": len(result.document.questions),
        "issue_count": len(result.issues),
        "blocking": bool(blocking_issues(result.issues)),
        "issues": [issue.model_dump() for issue in result.issues],
        "repairs": list(result.repairs),
        "is_current": True,
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
            "position": position,
            "question_type": q.question_type,
            "question_text": q.question_text,
            "options": list(q.options),
            "marks": q.marks,
            "group_marks": q.group_marks,
            "group_marks_scope": q.group_marks_scope,
            "answer": q.answer,
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
            superseded = self._supersede_older_runs(document_id, run_id)
        except Exception:
            # No transactions over REST: do not leave a run with no questions.
            self.client.table(TABLE_RUNS).delete().eq("id", run_id).execute()
            raise
        return SaveOutcome(document_id, run_id, count, superseded)

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


def connect(url: str, key: str) -> Any:
    """Build a Supabase client, failing with a plain message if the SDK is absent."""
    try:
        from supabase import create_client
    except ImportError as exc:
        raise StoreError("The supabase package is not installed: pip install supabase") from exc
    return create_client(url, key)
