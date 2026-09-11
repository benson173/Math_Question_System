from app.config import load_settings
from app.schemas import ExtractedDocument, ValidationIssue


class Repository:
    def __init__(self):
        self.settings = load_settings()

    def save_extracted_document(
        self,
        document: ExtractedDocument,
        issues: list[ValidationIssue],
    ) -> None:
        # Phase 1:
        # Supabase 由你自己做，所以這裏先 print。
        # 之後再改成 supabase.table(...).insert(...)

        print("=== SAVE DOCUMENT ===")
        print("File:", document.file_name)
        print("Pages:", document.page_count)
        print("Questions:", len(document.questions))

        print("=== QUESTIONS ===")
        for q in document.questions:
            print(q.source_question_id, q.question_text[:80])

        print("=== ISSUES ===")
        for issue in issues:
            print(issue.issue_code, issue.severity, issue.message)
