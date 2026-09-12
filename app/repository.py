"""The one place that saves data.

Repository is the storekeeper. Nothing else in the system writes to storage, so
when Supabase arrives only this file changes.
"""

from app.config import load_settings
from app.extraction_validator import blocking_issues
from app.schemas import ExtractionResult


class Repository:
    def __init__(self):
        self.settings = load_settings()

    def save_extraction_result(self, result: ExtractionResult) -> None:
        # Phase 1:
        # Supabase 由你自己做，所以這裏先 print。
        # 之後再改成 supabase.table(...).insert(...) 寫入
        #   source_documents / extraction_runs / questions

        document = result.document

        print("=== SAVE DOCUMENT ===")
        print("File:", document.file_name)
        print("Pages:", document.page_count)
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
            marks = "" if q.marks is None else f"  [{q.marks} marks]"
            print(f"{q.source_question_id}  p{q.page_start}-{q.page_end}  "
                  f"{q.question_text[:80]}{marks}")

        print("=== ISSUES ===")
        if not result.issues:
            print("(none)")
        for issue in result.issues:
            print(issue.issue_code, issue.severity, issue.message)

        blocking = blocking_issues(result.issues)
        if blocking:
            codes = ", ".join(sorted({issue.issue_code for issue in blocking}))
            print(f"=== BLOCKING: {codes} ===")
