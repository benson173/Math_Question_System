"""Parts that build on earlier parts: read, filled in, and checked."""

from __future__ import annotations

from app.extraction_repair import (
    previous_sibling,
    referenced_parts,
    repair_dependencies,
    says_hence,
)
from app.extraction_validator import validate_extraction
from app.schemas import ExtractedDocument, ExtractedQuestion


def question(qid, text, depends_on=None):
    return ExtractedQuestion(source_question_id=qid, page_start=1, page_end=1,
                             question_text=text, depends_on=depends_on or [])


def document(*questions):
    return ExtractedDocument(level="F4", file_name="s.pdf", page_count=1,
                             questions=list(questions))


def codes(doc):
    return sorted(i.issue_code for i in validate_extraction(doc))


# --- reading the words ------------------------------------------------------

def test_a_named_part_is_resolved_to_a_full_id():
    assert referenced_parts("利用 (a) 的結果，求 k。", "17(b)") == ["17(a)"]
    assert referenced_parts("Using the result of (a), solve for x.", "17(b)") == ["17(a)"]
    assert referenced_parts("From (b), find y.", "17(c)") == ["17(b)"]


def test_a_roman_part_is_resolved_under_the_same_letter():
    assert referenced_parts("由 (i) 可知，求 k。", "18(a)(ii)") == ["18(a)(i)"]


def test_a_part_never_references_itself():
    assert referenced_parts("利用 (b) 的結果。", "17(b)") == []


def test_a_bracket_with_no_cue_word_is_not_a_reference():
    # "(a)" here is a label in a shared stem, not a reference to it.
    assert referenced_parts("(a) 求 x。(b) 求 y。", "17(b)") == []


def test_hence_is_recognised_in_both_languages():
    assert says_hence("Hence, or otherwise, solve the equation.")
    assert says_hence("由此求 k 的值。")
    assert not says_hence("Henceforth we write f(x).")
    assert not says_hence("求 x 的值。")


def test_the_previous_sibling_is_the_part_before_under_the_same_parent():
    a, b, c, other = (question("17(a)", "x"), question("17(b)", "y"),
                      question("17(c)", "z"), question("18", "w"))
    doc = document(a, other, b, c)
    assert previous_sibling(b, doc.questions) == "17(a)"
    assert previous_sibling(c, doc.questions) == "17(b)"
    assert previous_sibling(a, doc.questions) is None
    assert previous_sibling(other, doc.questions) is None


# --- filling depends_on -----------------------------------------------------

def test_a_named_reference_is_filled_in_and_noted():
    doc = document(question("17(a)", "求 x。"), question("17(b)", "利用 (a) 的結果，求 k。"))
    repairs = repair_dependencies(doc)
    assert doc.questions[1].depends_on == ["17(a)"]
    assert "depends_on filled" in doc.questions[1].extraction_notes[0]
    assert repairs[0].reason == "named in the text"


def test_hence_fills_in_the_part_before():
    doc = document(question("17(a)", "求 x。"), question("17(b)", "Hence find y."))
    repair_dependencies(doc)
    assert doc.questions[1].depends_on == ["17(a)"]


def test_a_list_the_model_already_filled_is_left_alone():
    doc = document(question("17(a)", "求 x。"),
                   question("17(b)", "Hence find y.", depends_on=["17(a)"]))
    assert repair_dependencies(doc) == []
    assert doc.questions[1].extraction_notes == []


def test_a_reference_to_a_part_not_in_the_paper_is_not_filled():
    doc = document(question("17(b)", "利用 (a) 的結果。"))
    assert repair_dependencies(doc) == []
    assert doc.questions[0].depends_on == []


def test_hence_on_a_first_part_has_nothing_to_point_at():
    doc = document(question("17(a)", "Hence find x."))
    assert repair_dependencies(doc) == []


# --- what the validator says ------------------------------------------------

def test_a_correct_dependency_is_no_issue():
    doc = document(question("17(a)", "求 x。"),
                   question("17(b)", "Hence find y.", depends_on=["17(a)"]))
    assert codes(doc) == []


def test_depending_on_a_missing_part_is_reported():
    doc = document(question("17(b)", "求 y。", depends_on=["17(a)"]))
    assert "DEPENDENCY_UNKNOWN" in codes(doc)


def test_depending_on_a_parent_that_is_split_into_parts_is_fine():
    doc = document(question("18(a)(i)", "x"), question("18(a)(ii)", "y"),
                   question("18(b)", "z", depends_on=["18(a)"]))
    assert codes(doc) == []


def test_depending_on_itself_is_reported():
    doc = document(question("17(a)", "x", depends_on=["17(a)"]))
    assert "DEPENDENCY_SELF" in codes(doc)


def test_a_stated_dependency_left_empty_is_a_low_nudge():
    doc = document(question("17(a)", "求 x。"), question("17(b)", "由此求 y。"))
    issues = [i for i in validate_extraction(doc) if i.issue_code == "DEPENDENCY_UNMARKED"]
    assert len(issues) == 1 and issues[0].severity == "low"
    assert issues[0].source_question_id == "17(b)"


def test_after_the_repair_the_nudge_goes_away():
    doc = document(question("17(a)", "求 x。"), question("17(b)", "由此求 y。"))
    repair_dependencies(doc)
    assert "DEPENDENCY_UNMARKED" not in codes(doc)
