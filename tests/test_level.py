"""Reading the form (F1-F6) off a file name or a paper."""

from __future__ import annotations

import pytest

from app.extraction_validator import validate_extraction
from app.level import (
    LEVELS,
    find_levels,
    level_from_filename,
    level_from_paper,
    parse_level,
    resolve_level,
)
from app.schemas import ExtractedDocument, ExtractedQuestion


def codes(document) -> list[str]:
    return sorted({issue.issue_code for issue in validate_extraction(document)})


def document(file_name="F4-paper.pdf", level="F4", level_source="filename",
             level_text=None) -> ExtractedDocument:
    return ExtractedDocument(
        file_name=file_name, page_count=1, level=level,
        level_source=level_source, level_text=level_text,
        questions=[ExtractedQuestion(source_question_id="1", page_start=1,
                                     page_end=1, question_text="求 x。")],
    )


# --- how a form can be written ----------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("中一", "F1"),
    ("中四", "F4"),
    ("中五級", "F5"),
    ("中六年級", "F6"),
    ("S4", "F4"),
    ("S.4", "F4"),
    ("s4-2024-mock.pdf", "F4"),
    ("F.5", "F5"),
    ("F 3", "F3"),
    ("Form 4", "F4"),
    ("form4", "F4"),
    ("Secondary 6", "F6"),
    ("Sec 2", "F2"),
    ("2526_1st_S4MATH1.pdf", "F4"),
    ("Grade 7", "F1"),
    ("Grade 10", "F4"),
    ("Grade 12", "F6"),
])
def test_every_spelling_becomes_one_code(text, expected):
    assert parse_level(text) == expected
    assert expected in LEVELS


@pytest.mark.parametrize("text", [
    "2024-DSE-paper1.pdf",
    "mock-paper-2.pdf",
    "formula sheet",
    "其中一個答案",
    "S45",
    "maths4.pdf",
    "",
])
def test_text_with_no_form_gives_none(text):
    assert parse_level(text) is None


def test_two_different_forms_are_no_answer():
    # "中一至中三" is a range, not this paper's form.
    assert find_levels("中一至中三") == ["F1", "F3"]
    assert parse_level("中一至中三") is None


def test_the_same_form_written_twice_is_still_one_answer():
    assert parse_level("S4 數學 (中四)") == "F4"


def test_grades_below_seven_are_not_secondary_forms():
    assert parse_level("Grade 6") is None


# --- which source wins ------------------------------------------------------

def test_the_file_name_wins():
    resolved = resolve_level("S5-mock.pdf", "中四")
    assert (resolved.level, resolved.source) == ("F5", "filename")


def test_the_paper_answers_when_the_file_name_does_not():
    resolved = resolve_level("mock-paper-1.pdf", "中四")
    assert (resolved.level, resolved.source) == ("F4", "paper")


def test_neither_source_leaves_it_unknown():
    resolved = resolve_level("mock-paper-1.pdf", None)
    assert (resolved.level, resolved.source) == (None, None)


def test_unreadable_printed_text_is_not_guessed():
    assert level_from_paper("高中") is None
    assert level_from_filename("paper.pdf") is None


# --- what the validator says ------------------------------------------------

def test_a_known_form_is_no_issue():
    assert codes(document()) == []


def test_no_form_anywhere_is_a_low_nudge():
    issues = validate_extraction(document(file_name="paper.pdf", level=None,
                                          level_source=None))
    assert [i.issue_code for i in issues] == ["LEVEL_MISSING"]
    assert issues[0].severity == "low"
    assert "paper.pdf" in issues[0].message


def test_the_message_says_the_paper_was_unreadable():
    issues = validate_extraction(document(file_name="paper.pdf", level=None,
                                          level_source=None, level_text="高中"))
    assert "高中" in issues[0].message


def test_the_two_sources_disagreeing_is_reported():
    issues = validate_extraction(document(file_name="S5-mock.pdf", level="F5",
                                          level_source="filename", level_text="中四"))
    assert [i.issue_code for i in issues] == ["LEVEL_MISMATCH"]
    assert issues[0].severity == "medium"
    assert "F5" in issues[0].message and "F4" in issues[0].message


def test_the_two_sources_agreeing_is_silent():
    assert codes(document(file_name="S4-mock.pdf", level="F4",
                          level_source="filename", level_text="中四")) == []


def test_a_missing_form_never_blocks_ingestion():
    from app.extraction_validator import has_blocking_issues
    issues = validate_extraction(document(file_name="paper.pdf", level=None,
                                          level_source=None))
    assert has_blocking_issues(issues) is False


@pytest.mark.parametrize("text", ["當中一個", "集中一點", "其中一項"])
def test_phrases_that_merely_contain_zhong_yi_are_not_form_one(text):
    assert parse_level(text) is None
