"""The one place that saves data.

Repository is the storekeeper. Nothing else in the system writes to storage.

With SUPABASE_URL and SUPABASE_SECRET_KEY set, every extraction is written to
the three tables in docs/supabase_schema.sql. Without them it prints, as it
always did, so the pipeline still works on a laptop with no database.
"""

from __future__ import annotations

from app.config import load_settings
from app.extraction_validator import blocking_issues
from app.schemas import ExtractionResult
from app.supabase_store import SaveOutcome, SupabaseStore, connect


class Repository:
    def __init__(self, verbose: bool = True, store: SupabaseStore | None = None):
        # Printing every question in full is what you want for one PDF and
        # unreadable for fifty; a batch prints one line instead and leaves the
        # detail to each paper's own report.
        self.verbose = verbose
        self.settings = load_settings()
        self.store = store if store is not None else self._store_from_settings()

    def _store_from_settings(self) -> SupabaseStore | None:
        url, key = self.settings.supabase_url, self.settings.supabase_secret_key
        if not url or not key or url.startswith("put_") or key.startswith("put_"):
            return None
        return SupabaseStore(connect(url, key))

    @property
    def writes_to_database(self) -> bool:
        return self.store is not None

    def save_extraction_result(self, result: ExtractionResult) -> SaveOutcome | None:
        if self.verbose:
            self._print_in_full(result)
        else:
            self._save_quietly(result)

        if self.store is None:
            return None

        outcome = self.store.save(result)
        superseded = f", superseded {outcome.superseded_runs} earlier run(s)" \
            if outcome.superseded_runs else ""
        print(f"Supabase: run {outcome.run_id[:8]} with {outcome.questions} questions "
              f"for document {outcome.document_id[:8]}{superseded}")
        return outcome

    def _print_in_full(self, result: ExtractionResult) -> None:
        document = result.document

        print("=== SAVE DOCUMENT ===")
        print("File:", document.file_name)
        print("Pages:", document.page_count)
        print("Level:", f"{document.level} (from {document.level_source})"
                        if document.level else "unknown")
        print("Questions:", len(document.questions))
        if result.source:
            print("SHA256:", result.source.sha256)
            print("Size:", result.source.byte_size, "bytes")
        if result.run:
            print("Run:", result.run.run_id)
            print("Model:", result.run.model)
            print("Extraction version:", result.run.extraction_version)
            print("Question object version:", result.run.question_object_version)

        print("=== QUESTIONS ===")
        for q in document.questions:
            # Printed in full, on its own lines. Truncating to a preview made
            # sub-questions of the same parent look identical (they share a
            # stem) and cut markdown tables mid-row, which read as extraction
            # failures when the data was fine.
            labels = []
            if q.marks is not None:
                labels.append(f"{q.marks} marks")
            if q.diagram_required:
                labels.append("diagram")
            suffix = f"  [{', '.join(labels)}]" if labels else ""
            print(f"--- {q.source_question_id}  p{q.page_start}-{q.page_end}{suffix}")

            for line in q.question_text.splitlines():
                print(f"    {line}")
            if q.answer:
                print(f"    ANSWER: {q.answer}")
            if q.worked_solution:
                print(f"    SOLUTION: {q.worked_solution}")
            for note in q.extraction_notes:
                print(f"    NOTE: {note}")
            print()

        print("=== ISSUES ===")
        if not result.issues:
            print("(none)")
        for issue in result.issues:
            print(issue.issue_code, issue.severity, issue.message)

        blocking = blocking_issues(result.issues)
        if blocking:
            codes = ", ".join(sorted({issue.issue_code for issue in blocking}))
            print(f"=== BLOCKING: {codes} ===")

    def _save_quietly(self, result: ExtractionResult) -> None:
        document = result.document
        parts = [document.level or "level unknown", f"{len(document.questions)} questions"]
        if result.issues:
            parts.append(f"{len(result.issues)} issues")
        if result.diagrams:
            parts.append(f"{len(result.diagrams)} diagrams")
        if result.tables:
            parts.append(f"{len(result.tables)} tables")
        print(f"Saved {document.file_name}: {', '.join(parts)}")
