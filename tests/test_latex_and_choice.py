"""Two faults three real papers exposed.

A LaTeX backslash the model failed to escape in its JSON arrives as the control
character that escape denotes, destroying the command. And a multiple-choice
paper had its options sitting in prose, where nothing downstream can read them.
"""

from __future__ import annotations

import json

import pytest

from app.extraction_repair import (
    EATEN_BACKSLASH,
    find_control_characters,
    repair_control_characters,
    restore_eaten_backslashes,
)
from app.extraction_validator import looks_like_multiple_choice, validate_extraction
from app.schemas import ExtractedDocument, ExtractedQuestion


def question(question_id="1", text="求 x 的值。", **overrides) -> ExtractedQuestion:
    defaults = dict(source_question_id=question_id, page_start=1, page_end=1,
                    question_text=text)
    defaults.update(overrides)
    return ExtractedQuestion(**defaults)


def codes(questions) -> list[str]:
    document = ExtractedDocument(level="F4", file_name="s.pdf", page_count=1,
                                 questions=list(questions))
    return sorted({issue.issue_code for issue in validate_extraction(document)})


def as_json_would_decode(latex: str) -> str:
    """What arrives when the model writes a single backslash in its JSON."""
    return json.loads('{"t": "' + latex + ' x"}')["t"]


# --- eaten backslashes ------------------------------------------------------

@pytest.mark.parametrize("latex, letter", [
    ("\\frac", "f"), ("\\forall", "f"), ("\\beta", "b"), ("\\binom", "b"),
])
def test_an_eaten_backslash_is_restored(latex, letter):
    damaged = as_json_would_decode(latex)
    assert find_control_characters(damaged)

    repaired, restored = restore_eaten_backslashes(damaged)
    assert restored == {letter: 1}
    assert repaired == f"{latex} x"
    assert find_control_characters(repaired) == {}


@pytest.mark.parametrize("latex", ["\\vec", "\\alpha", "\\sum"])
def test_other_commands_fail_loudly_instead(latex):
    # JSON has no such escape, so the response is rejected rather than quietly
    # corrupted - which is why they are not in the repair map.
    with pytest.raises(json.JSONDecodeError):
        as_json_would_decode(latex)


def test_only_the_two_unambiguous_escapes_are_rewritten():
    assert set(EATEN_BACKSLASH) == {"\x0c", "\x08"}


@pytest.mark.parametrize("text", ["第一行\n第二行", "a b c", ""])
def test_ordinary_text_carries_no_control_characters(text):
    assert find_control_characters(text) == {}


def test_a_tab_is_reported_but_never_rewritten():
    # \t begins \times and \theta, but is also ordinary whitespace.
    assert find_control_characters("a\tb") == {"\t": 1}
    assert restore_eaten_backslashes("a\tb") == ("a\tb", {})


def test_the_issue_names_the_cause():
    damaged = as_json_would_decode("\\frac")
    issues = [i for i in validate_extraction(
        ExtractedDocument(level="F4", file_name="s.pdf", page_count=1,
                          questions=[question("2", damaged)]))
        if i.issue_code == "CONTROL_CHARACTER"]
    assert len(issues) == 1
    assert issues[0].severity == "high"
    assert "unescaped" in issues[0].message


def test_repair_touches_only_damaged_questions():
    good = "化簡 \\(\\frac{x}{y}\\)。"
    document = ExtractedDocument(level="F4", file_name="s.pdf", page_count=1, questions=[
        question("1", good),
        question("2", as_json_would_decode("\\frac")),
    ])

    repairs = repair_control_characters(document)
    assert [r.source_question_id for r in repairs] == ["2"]
    assert document.questions[0].question_text == good
    assert not document.questions[0].extraction_notes
    assert len(document.questions[1].extraction_notes) == 1


def test_repair_is_idempotent():
    document = ExtractedDocument(level="F4", file_name="s.pdf", page_count=1,
                                 questions=[question("1", as_json_would_decode("\\frac"))])
    assert repair_control_characters(document)
    assert repair_control_characters(document) == []


# --- multiple choice --------------------------------------------------------

MC_QUESTION = ("\\( \\frac{81^{1-n}}{27^{2n}} = \\)\n\n"
               "A. \\( 3^{1-3n} \\) 。\nB. \\( \\frac{1}{3^{3n-2}} \\) 。\n"
               "C. \\( \\frac{1}{3^{5n-2}} \\) 。\nD. \\( \\frac{1}{3^{10n-4}} \\) 。")


def test_printed_options_are_recognised():
    assert looks_like_multiple_choice(MC_QUESTION)


@pytest.mark.parametrize("text", [
    "圖中，通過 A(5, 4) 及 B 的直線垂直於通過 A 及 C(13, 10) 的直線。",
    "圖中，A、B、D、E 和 F 均是圓上的點，且 AD // FE。",
    "圖中，D 是 AB 上的一點使得 ∠BAC = ∠BCD。證明 △ABC ~ △CBD。",
    "求平均數。\n\n| 分數 | 0 | 1 |\n| --- | --- | --- |\n| 人數 | 14 | 9 |",
])
def test_points_and_labels_are_not_mistaken_for_options(text):
    assert looks_like_multiple_choice(text) is False


def test_options_left_in_prose_are_reported():
    assert codes([question("1", MC_QUESTION)]) == ["OPTIONS_NOT_SEPARATED"]


def test_a_choice_question_without_options_is_reported():
    assert codes([question("1", "下列何者正確？",
                           question_type="multiple_choice")]) == ["OPTIONS_MISSING"]


def test_a_properly_structured_choice_question_is_clean():
    assert codes([question("1", "下列何者正確？", question_type="multiple_choice",
                           options=["3^{1-3n}", "2", "1", "0"])]) == []


def test_an_open_question_is_not_checked_for_options():
    assert codes([question("1", "求 x 的值。")]) == []
