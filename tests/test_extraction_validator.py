import pytest

from app.extraction_validator import (
    blocking_issues,
    find_broken_powers,
    find_malformed_tables,
    find_ragged_tables,
    find_repeated_sentences,
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


# --- tables -----------------------------------------------------------------

GOOD_TABLE = ("在某次大抽獎中…\n\n"
              "| 球 | 現金獎 |\n| --- | --- |\n| 黑色 | $22 |\n| 白色 | $0 |\n\n"
              "求隨機抽取一次的期望現金獎。")

# What Gemini actually produced when the prompt did not pin the format.
BAD_TABLE = ("在某次大抽獎中…\n\n"
             "球 | 現金獎\n黑色 | $22\n綠色 | $10\n白色 | $0\n\n"
             "求隨機抽取一次的期望現金獎。")

STEM_AND_LEAF = ("以下的幹葉圖顯示…\n\n"
                 "幹（十位） | 葉（個位）\n0 | 5 5 6 8 9\n1 | 0 1 2 4\n\n求平均數。")


def test_a_proper_markdown_table_is_accepted():
    assert find_malformed_tables(GOOD_TABLE) == 0


def test_a_table_without_a_separator_row_is_caught():
    assert find_malformed_tables(BAD_TABLE) == 1


def test_a_stem_and_leaf_block_is_caught():
    assert find_malformed_tables(STEM_AND_LEAF) == 1


@pytest.mark.parametrize("text", [
    "圖中，O 是 △ABC 的外心。求 OA。",
    "某筆盒內有 6 支藍色筆。\n抽出的筆是藍色或黑色。",
    "求 |x - 3| 的值。",
    r"化簡 \(\frac{a^2}{b^5}\)。",
])
def test_prose_is_not_mistaken_for_a_table(text):
    assert find_malformed_tables(text) == 0


def test_malformed_table_is_reported_against_the_question(make_document, make_question):
    document = make_document([make_question(question_text=BAD_TABLE)])
    issues = [i for i in validate_extraction(document) if i.issue_code == "MALFORMED_TABLE"]
    assert len(issues) == 1
    assert issues[0].severity == "medium"


def test_malformed_table_does_not_block(make_document, make_question):
    document = make_document([make_question(question_text=BAD_TABLE)])
    assert has_blocking_issues(validate_extraction(document)) is False


# --- ragged tables ----------------------------------------------------------

# A printed grid with a two-level header, as Gemini rendered it: the merged
# header cannot be expressed, so the rows stop agreeing on cell count.
RAGGED_TABLE = ("在下表列出所有可能結果。\n\n"
                "| | | 第二枚勻稱骰子 | | | | |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| | | 1 | 2 | 3 | 4 | 5 | 6 |\n"
                "| 第一枚勻稱骰子 | 1 | (1, 1) | (1, 2) | | | | |\n")

FLATTENED_TABLE = ("在下表列出所有可能結果。\n\n"
                   "| 第一枚勻稱骰子 / 第二枚勻稱骰子 | 1 | 2 | 3 | 4 | 5 | 6 |\n"
                   "| --- | --- | --- | --- | --- | --- | --- |\n"
                   "| 1 | (1, 1) | (1, 2) | | | | |\n"
                   "| 2 | | | | | | |\n")


def test_a_ragged_table_is_found():
    assert find_ragged_tables(RAGGED_TABLE) == [1]


def test_a_ragged_table_is_not_also_called_malformed():
    # It has a separator row; the fault is the cell counts, and the message
    # needs to say so.
    assert find_malformed_tables(RAGGED_TABLE) == 0


def test_flattening_the_header_clears_it():
    assert find_ragged_tables(FLATTENED_TABLE) == []
    assert find_malformed_tables(FLATTENED_TABLE) == 0


@pytest.mark.parametrize("text", [GOOD_TABLE, STEM_AND_LEAF, BAD_TABLE])
def test_well_formed_and_separator_less_tables_are_not_ragged(text):
    assert find_ragged_tables(text) == []


def test_two_tables_separated_by_a_blank_line_are_independent():
    text = ("| 重量 (g) | 頻數 |\n| --- | --- |\n| 201 – 210 | a |\n\n"
            "| 重量少於 (g) | 累積頻數 |\n| --- | --- |\n| 210.5 | 5 |")
    assert find_ragged_tables(text) == []
    assert find_malformed_tables(text) == 0


def test_ragged_table_is_reported_with_advice(make_document, make_question):
    document = make_document([make_question(source_question_id="12(a)",
                                            question_text=RAGGED_TABLE)])
    issues = [i for i in validate_extraction(document) if i.issue_code == "RAGGED_TABLE"]
    assert len(issues) == 1
    assert issues[0].severity == "medium"
    assert "merged cells" in issues[0].message


# --- text repeated inside one question --------------------------------------

# 19(c) as extracted: the part's own question also sits in the shared stem.
REPEATED = ("圖中，O 是原點。L 分別與 x 軸和 y 軸相交於點 A 和點 B。求 △OAB 的面積。\n"
            "求 △OAB 的面積。")


def test_repeated_sentence_is_found():
    assert find_repeated_sentences(REPEATED) == ["求 △OAB 的面積"]


def test_distinct_sentences_are_not_flagged():
    text = "圖中，O 是原點。求 △OAB 的面積。\n求直線 L 的斜率。"
    assert find_repeated_sentences(text) == []


def test_table_rows_are_not_treated_as_sentences():
    assert find_repeated_sentences(GOOD_TABLE) == []


def test_short_fragments_are_ignored():
    assert find_repeated_sentences("求 x。\n求 x。") == []


def test_repeated_text_is_reported(make_document, make_question):
    document = make_document([make_question(source_question_id="19(c)",
                                            question_text=REPEATED)])
    issues = [i for i in validate_extraction(document)
              if i.issue_code == "REPEATED_TEXT_IN_QUESTION"]
    assert len(issues) == 1 and issues[0].source_question_id == "19(c)"


# --- marks ------------------------------------------------------------------

def test_missing_marks_reported_when_the_paper_marks_others(make_document, make_question):
    document = make_document([
        make_question(source_question_id="1", marks=3),
        make_question(source_question_id="2(a)"),
    ])
    issues = [i for i in validate_extraction(document) if i.issue_code == "MARKS_MISSING"]
    assert [i.source_question_id for i in issues] == ["2(a)"]
    assert issues[0].severity == "low"


def test_group_marks_count_as_marks(make_document, make_question):
    document = make_document([
        make_question(source_question_id="1", marks=3),
        make_question(source_question_id="2(a)", group_marks=4, group_marks_scope="2"),
    ])
    assert "MARKS_MISSING" not in codes(document)


def test_a_paper_printing_no_marks_at_all_is_not_flagged(make_document, make_question):
    document = make_document([
        make_question(source_question_id="1"),
        make_question(source_question_id="2"),
    ])
    assert "MARKS_MISSING" not in codes(document)


# --- diagram regions --------------------------------------------------------

def diagram_codes(document) -> list[str]:
    return sorted({i.issue_code for i in validate_extraction(document)
                   if "DIAGRAM" in i.issue_code})


def test_diagram_without_a_region_is_reported(make_document, make_question):
    document = make_document([make_question(diagram_required=True)])
    assert diagram_codes(document) == ["DIAGRAM_REGION_UNUSABLE"]


def test_diagram_with_a_malformed_region_is_reported(make_document, make_question):
    from app.schemas import PageRegion
    bad = PageRegion(page=1, y_min=600, x_min=900, y_max=200, x_max=100)
    document = make_document([make_question(diagram_required=True, diagram_region=bad)])
    assert diagram_codes(document) == ["DIAGRAM_REGION_UNUSABLE"]


def test_diagram_with_a_good_region_is_clean(make_document, make_question):
    from app.schemas import PageRegion
    good = PageRegion(page=1, y_min=200, x_min=100, y_max=600, x_max=900)
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
