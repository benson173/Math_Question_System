import pytest

from app.extraction_validator import (
    blocking_issues,
    find_broken_powers,
    has_blocking_issues,
    validate_extraction,
)
from app.schemas import ValidationIssue


def codes(document) -> list[str]:
    return sorted({issue.issue_code for issue in validate_extraction(document)})


# --- the checks the guide asked for -----------------------------------------

def test_clean_document_has_no_issues(make_document):
    assert codes(make_document()) == []


def test_no_questions_is_critical(make_document):
    issues = validate_extraction(make_document(questions=[]))
    assert [i.issue_code for i in issues] == ["NO_QUESTIONS_FOUND"]
    assert issues[0].severity == "critical"


def test_empty_question_text_is_critical(make_document, make_question):
    issues = validate_extraction(make_document([make_question(question_text="   ")]))
    empty = [i for i in issues if i.issue_code == "EMPTY_QUESTION_TEXT"]
    assert empty and empty[0].severity == "critical"


def test_duplicate_question_id_is_reported(make_document, make_question):
    assert "DUPLICATE_QUESTION_ID" in codes(
        make_document([make_question(), make_question()]))


def test_invalid_page_count_is_reported(make_document):
    assert "PAGE_COUNT_INVALID" in codes(make_document(page_count=0))


def test_invalid_page_number_is_reported(make_document, make_question):
    assert "PAGE_NUMBER_INVALID" in codes(
        make_document([make_question(page_start=0, page_end=0)]))


def test_page_range_backwards_is_reported(make_document, make_question):
    assert "PAGE_RANGE_INVALID" in codes(
        make_document([make_question(page_start=3, page_end=2)], page_count=3))


# --- sub-question ids, 1(a) convention --------------------------------------

def test_sub_question_ids_are_not_duplicates(make_document, make_question):
    document = make_document([
        make_question(source_question_id="1(a)"),
        make_question(source_question_id="1(b)"),
        make_question(source_question_id="1(b)(i)"),
    ])
    assert "DUPLICATE_QUESTION_ID" not in codes(document)


def test_repeated_sub_question_id_is_reported(make_document, make_question):
    document = make_document([
        make_question(source_question_id="1(a)"),
        make_question(source_question_id="1(a)"),
    ])
    assert "DUPLICATE_QUESTION_ID" in codes(document)


def test_blank_question_id_is_reported(make_document, make_question):
    assert "MISSING_QUESTION_ID" in codes(make_document([make_question(source_question_id=" ")]))


# --- broken power notation ---------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("Factorise 1 - 225x2.", ["x2"]),
    # A correct power elsewhere in the same question must not hide a broken one.
    ("Factorise 1 - 225x2, then simplify x².", ["x2"]),
    # Any variable, not just x.
    ("Expand 4y2 + a2 - x3.", ["a2", "x3", "y2"]),
    # Broken units count too.
    ("The area is 25cm2.", ["m2"]),
    # Properly written powers are never flagged.
    ("Simplify x² + 1.", []),
    ("Simplify x^2 + 1.", []),
    ("Simplify x**2 + 1.", []),
    # Dimensions and question labels are not broken powers.
    ("Draw a 2x2 grid.", []),
    ("In Q2, find the value of n.", []),
    ("Primary 6 paper P2.", []),
])
def test_find_broken_powers(text, expected):
    assert sorted(set(find_broken_powers(text))) == expected


def test_broken_power_issue_names_what_it_found(make_document, make_question):
    issues = validate_extraction(make_document([make_question(question_text="4y2 + a2")]))
    power = next(i for i in issues if i.issue_code == "POSSIBLE_BROKEN_POWER")
    assert "a2" in power.message and "y2" in power.message
    assert power.severity == "medium"


# --- checks added beyond the guide ------------------------------------------

def test_page_beyond_document_is_reported(make_document, make_question):
    document = make_document([make_question(page_start=99, page_end=99)], page_count=3)
    assert "PAGE_OUT_OF_RANGE" in codes(document)


def test_page_within_document_is_not_reported(make_document, make_question):
    document = make_document([make_question(page_start=3, page_end=3)], page_count=3)
    assert "PAGE_OUT_OF_RANGE" not in codes(document)


def test_negative_marks_are_reported(make_document, make_question):
    assert "MARKS_INVALID" in codes(make_document([make_question(marks=-5)]))


def test_zero_and_positive_marks_are_accepted(make_document, make_question):
    for marks in (0, 0.5, 2, 10):
        assert "MARKS_INVALID" not in codes(make_document([make_question(marks=marks)]))


def test_too_few_questions_for_page_count_is_reported(make_document, make_question):
    document = make_document([make_question()], page_count=30)
    assert "SUSPICIOUSLY_FEW_QUESTIONS" in codes(document)


@pytest.mark.parametrize("page_count", [1, 2, 3, 4])
def test_density_check_is_skipped_for_short_documents(
    make_document, make_question, page_count
):
    # A short paper really can hold a single long question.
    document = make_document([make_question()], page_count=page_count)
    assert "SUSPICIOUSLY_FEW_QUESTIONS" not in codes(document)


def test_short_document_with_one_question_is_completely_clean(
    make_document, make_question
):
    document = make_document([make_question(page_start=3, page_end=3)], page_count=3)
    assert codes(document) == []


def test_enough_questions_is_not_reported(make_document, make_question):
    questions = [
        make_question(source_question_id=str(n), page_start=n, page_end=n)
        for n in range(1, 11)
    ]
    assert "SUSPICIOUSLY_FEW_QUESTIONS" not in codes(make_document(questions, page_count=10))


# --- diagram regions --------------------------------------------------------

def diagram_codes(document) -> list[str]:
    return sorted({i.issue_code for i in validate_extraction(document)
                   if "DIAGRAM" in i.issue_code})


def test_diagram_without_a_region_is_reported(make_document, make_question):
    document = make_document([make_question(diagram_required=True)])
    assert diagram_codes(document) == ["DIAGRAM_REGION_UNUSABLE"]


def test_diagram_with_a_malformed_region_is_reported(make_document, make_question):
    from app.schemas import DiagramRegion
    bad = DiagramRegion(page=1, y_min=600, x_min=900, y_max=200, x_max=100)
    document = make_document([make_question(diagram_required=True, diagram_region=bad)])
    assert diagram_codes(document) == ["DIAGRAM_REGION_UNUSABLE"]


def test_diagram_with_a_good_region_is_clean(make_document, make_question):
    from app.schemas import DiagramRegion
    good = DiagramRegion(page=1, y_min=200, x_min=100, y_max=600, x_max=900)
    document = make_document([make_question(diagram_required=True, diagram_region=good)])
    assert diagram_codes(document) == []


def test_questions_without_diagrams_are_not_checked(make_document, make_question):
    assert diagram_codes(make_document([make_question(diagram_required=False)])) == []


def test_diagram_issue_is_not_blocking(make_document, make_question):
    # A missing box falls back to a full-page render; that is not a failure.
    document = make_document([make_question(diagram_required=True)])
    assert has_blocking_issues(validate_extraction(document)) is False


# --- blocking helpers -------------------------------------------------------

def issue(severity):
    return ValidationIssue(issue_code="X", severity=severity, message="m")


def test_only_critical_issues_block():
    assert has_blocking_issues([issue("critical")]) is True
    assert has_blocking_issues([issue("high"), issue("medium"), issue("low")]) is False
    assert has_blocking_issues([]) is False


def test_blocking_issues_returns_the_critical_ones():
    issues = [issue("high"), issue("critical"), issue("medium")]
    assert [i.severity for i in blocking_issues(issues)] == ["critical"]


def test_empty_extraction_blocks(make_document):
    assert has_blocking_issues(validate_extraction(make_document(questions=[]))) is True


def test_good_extraction_does_not_block(make_document):
    assert has_blocking_issues(validate_extraction(make_document())) is False
