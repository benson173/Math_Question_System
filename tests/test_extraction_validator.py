from app.extraction_validator import validate_extraction
from app.schemas import ExtractedDocument, ExtractedQuestion


def make_question(**overrides) -> ExtractedQuestion:
    defaults = dict(
        source_question_id="1",
        page_start=1,
        page_end=1,
        question_text="Factorise 1 - 225x².",
    )
    defaults.update(overrides)
    return ExtractedQuestion(**defaults)


def make_document(questions, page_count=1) -> ExtractedDocument:
    return ExtractedDocument(
        file_name="sample.pdf",
        page_count=page_count,
        questions=questions,
    )


def codes(document: ExtractedDocument) -> list[str]:
    return [issue.issue_code for issue in validate_extraction(document)]


def test_clean_document_has_no_issues():
    assert codes(make_document([make_question()])) == []


def test_no_questions_is_critical():
    assert "NO_QUESTIONS_FOUND" in codes(make_document([]))


def test_empty_question_text_is_reported():
    assert "EMPTY_QUESTION_TEXT" in codes(make_document([make_question(question_text="   ")]))


def test_duplicate_question_id_is_reported():
    document = make_document([make_question(), make_question()])
    assert "DUPLICATE_QUESTION_ID" in codes(document)


def test_invalid_page_count_is_reported():
    assert "PAGE_COUNT_INVALID" in codes(make_document([make_question()], page_count=0))


def test_invalid_page_number_is_reported():
    assert "PAGE_NUMBER_INVALID" in codes(make_document([make_question(page_start=0, page_end=0)]))


def test_page_range_backwards_is_reported():
    assert "PAGE_RANGE_INVALID" in codes(make_document([make_question(page_start=3, page_end=2)], page_count=3))


def test_broken_power_notation_is_reported():
    document = make_document([make_question(question_text="Factorise 1 - 225x2.")])
    assert "POSSIBLE_BROKEN_POWER" in codes(document)


def test_correct_power_notation_is_not_reported():
    for text in ["Simplify x² + 1.", "Simplify x^2 + 1."]:
        document = make_document([make_question(question_text=text)])
        assert "POSSIBLE_BROKEN_POWER" not in codes(document)
