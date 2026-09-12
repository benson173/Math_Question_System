"""Delimiting a formula the model left bare.

A displayed formula written without \\( \\) renders nowhere - not in the
Markdown report, not in the web viewer, not in whatever a teacher pastes it
into. Two rounds of prompt instruction did not stop it, so a whole line that is
nothing but maths is now wrapped here. LaTeX inline in a sentence is still only
reported: where the maths ends inside prose is a guess.
"""

from __future__ import annotations

import pytest

from app.extraction_repair import (
    is_bare_formula_line,
    repair_undelimited_latex,
    wrap_bare_formulas,
)
from app.extraction_validator import find_undelimited_latex, validate_extraction
from app.schemas import ExtractedDocument, ExtractedQuestion


# Question 18 of the second S4 paper, as extracted.
BARE_FORMULA = r"L = 10 \log \frac{I}{10^{-12}}"
Q18 = ("聲音強級 L（單位是 dB）可用以下公式表示：\n"
       + BARE_FORMULA + "\n"
       "其中 I 是聲音強度和 I > 0。\n"
       "若一個班房內的聲音強級為 81 dB，求聲音強度。")


def question(question_id, text) -> ExtractedQuestion:
    return ExtractedQuestion(source_question_id=question_id, page_start=9,
                             page_end=9, question_text=text)


def document(questions) -> ExtractedDocument:
    return ExtractedDocument(file_name="s.pdf", page_count=14,
                             questions=list(questions))


# --- which lines qualify ----------------------------------------------------

@pytest.mark.parametrize("line", [
    BARE_FORMULA,
    r"P(n) = Ar^{n}",
    r"Q(m) = 2Ar^{\frac{n}{2}}",
])
def test_a_line_that_is_only_maths_qualifies(line):
    assert is_bare_formula_line(line) is True


@pytest.mark.parametrize("line", [
    r"L = \( 10 \log \frac{I}{10^{-12}} \)",   # already delimited
    r"$$ x^{2} $$",                            # delimited another way
    "其中 I 是聲音強度和 I > 0。",                 # prose
    r"把 y = \log_a bx 的圖像記為 G。",            # maths inline in prose
    r"簡化 i^{1029} - i^{1026}。",
    "L = 10 log I",                            # no LaTeX at all
    "",
    "   ",
])
def test_everything_else_is_left_alone(line):
    assert is_bare_formula_line(line) is False


# --- wrapping ---------------------------------------------------------------

def test_the_formula_is_wrapped_and_the_rest_untouched():
    wrapped_text, wrapped = wrap_bare_formulas(Q18)
    assert wrapped == [BARE_FORMULA]
    assert wrapped_text.split("\n")[1] == r"\( " + BARE_FORMULA + r" \)"

    before, after = Q18.split("\n"), wrapped_text.split("\n")
    assert [l for i, l in enumerate(after) if i != 1] == \
           [l for i, l in enumerate(before) if i != 1]


def test_wrapping_clears_the_issue():
    wrapped_text, _ = wrap_bare_formulas(Q18)
    assert find_undelimited_latex(Q18)          # was flagged
    assert find_undelimited_latex(wrapped_text) == []


def test_maths_inline_in_prose_is_reported_not_wrapped():
    original = r"把 y = \log_a bx 的圖像記為 G。已知 G 通過點 (3, 1)。"
    doc = document([question("19", original)])

    assert repair_undelimited_latex(doc) == []
    assert doc.questions[0].question_text == original
    assert "LATEX_NOT_DELIMITED" in {i.issue_code for i in validate_extraction(doc)}


# --- across a document ------------------------------------------------------

def test_only_affected_questions_change():
    doc = document([question("18(a)", Q18), question("18(b)", Q18),
                    question("9", "求 x 的值。")])

    repairs = repair_undelimited_latex(doc)
    assert sorted(r.source_question_id for r in repairs) == ["18(a)", "18(b)"]
    assert doc.questions[2].question_text == "求 x 的值。"
    assert doc.questions[2].extraction_notes == []
    assert len(doc.questions[0].extraction_notes) == 1


def test_the_note_says_what_happened():
    doc = document([question("18(a)", Q18)])
    repair_undelimited_latex(doc)
    note = doc.questions[0].extraction_notes[0]
    assert "wrapped" in note and "render" in note


def test_a_repaired_paper_reports_no_latex_issue():
    doc = document([question("18(a)", Q18)])
    repair_undelimited_latex(doc)
    assert "LATEX_NOT_DELIMITED" not in {i.issue_code for i in validate_extraction(doc)}


def test_repair_is_idempotent():
    doc = document([question("18(a)", Q18)])
    assert repair_undelimited_latex(doc)
    assert repair_undelimited_latex(doc) == []
