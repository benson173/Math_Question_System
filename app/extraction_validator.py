from app.schemas import ExtractedDocument, ValidationIssue


def validate_extraction(document: ExtractedDocument) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    if document.page_count <= 0:
        issues.append(ValidationIssue(
            issue_code="PAGE_COUNT_INVALID",
            severity="high",
            message="Document page_count is invalid.",
        ))

    if not document.questions:
        issues.append(ValidationIssue(
            issue_code="NO_QUESTIONS_FOUND",
            severity="critical",
            message="No questions were extracted.",
        ))

    seen_ids = set()

    for q in document.questions:
        if not q.question_text.strip():
            issues.append(ValidationIssue(
                issue_code="EMPTY_QUESTION_TEXT",
                severity="critical",
                message=f"Question {q.source_question_id} has empty text.",
            ))

        if q.source_question_id in seen_ids:
            issues.append(ValidationIssue(
                issue_code="DUPLICATE_QUESTION_ID",
                severity="medium",
                message=f"Duplicate question id: {q.source_question_id}",
            ))

        seen_ids.add(q.source_question_id)

        if q.page_start <= 0 or q.page_end <= 0:
            issues.append(ValidationIssue(
                issue_code="PAGE_NUMBER_INVALID",
                severity="high",
                message=f"Question {q.source_question_id} has invalid page number.",
            ))

        if q.page_end < q.page_start:
            issues.append(ValidationIssue(
                issue_code="PAGE_RANGE_INVALID",
                severity="high",
                message=f"Question {q.source_question_id} page_end is before page_start.",
            ))

        if "x2" in q.question_text and "x²" not in q.question_text and "x^2" not in q.question_text:
            issues.append(ValidationIssue(
                issue_code="POSSIBLE_BROKEN_POWER",
                severity="medium",
                message=f"Question {q.source_question_id} may have broken power notation.",
            ))

    return issues
