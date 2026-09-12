"""Comparing two runs over the same PDF."""

from __future__ import annotations

import pytest

from app.extraction_diff import compare_extractions, describe_text_change, render_diff
from app.schemas import (
    ExtractedDocument,
    ExtractedQuestion,
    ExtractionResult,
    ExtractionRun,
    PageRegion,
    SourceDocument,
)


# Question 20(b) as two runs produced it. Three runs said "18 cm"; one added
# words that are not on the page, with a note asserting they are.
Q20B_BEFORE = "已知 A 的高及底半徑分別為 13 cm 及 27 cm。嘉欣得知 B 的底半徑為 18 cm。"
Q20B_AFTER = "已知 A 的高及底半徑分別為 13 cm 及 27 cm。嘉欣得知 B 的底半徑為 B 為 18 cm。"

# The same expression with U+2212 and then U+2013 - indistinguishable by eye.
MINUS_BEFORE = "因式分解\n7r − 21s"
MINUS_AFTER = "因式分解\n7r – 21s"


def question(question_id, text, *, marks=None, tables=0) -> ExtractedQuestion:
    return ExtractedQuestion(
        source_question_id=question_id, page_start=1, page_end=1, question_text=text,
        marks=marks,
        table_regions=[PageRegion(page=1, y_min=1, x_min=1, y_max=9, x_max=9)] * tables,
    )


def result(questions, sha256="a" * 64) -> ExtractionResult:
    return ExtractionResult(
        document=ExtractedDocument(level="F4", file_name="sample.pdf", page_count=12,
                                   questions=list(questions)),
        source=SourceDocument(file_name="sample.pdf", sha256=sha256,
                              page_count=12, byte_size=1),
        run=ExtractionRun(run_id="r1", extracted_at="t", extraction_version="QEE_v1",
                          question_object_version="QOS_v1", model="m"),
    )


# --- what only a comparison can find ----------------------------------------

def test_invented_words_are_found():
    diff = compare_extractions(result([question("20(b)", Q20B_BEFORE)]),
                               result([question("20(b)", Q20B_AFTER)]))
    assert [d.source_question_id for d in diff.changed] == ["20(b)"]
    assert "{+B 為 +}" in diff.changed[0].changes[0].detail


def test_a_swapped_dash_is_found():
    diff = compare_extractions(result([question("2(a)", MINUS_BEFORE)]),
                               result([question("2(a)", MINUS_AFTER)]))
    detail = diff.changed[0].changes[0].detail
    assert "[-−-]" in detail and "{+–+}" in detail


# --- agreement --------------------------------------------------------------

def test_identical_runs_agree_completely():
    questions = [question("1", "化簡。"), question("7", "幹葉圖。")]
    diff = compare_extractions(result(questions), result(questions))
    assert diff.is_clean
    assert diff.agreement == 1.0
    assert "agree on every question" in render_diff(diff, "a", "b")


def test_agreement_is_the_share_of_identical_questions():
    before = [question(str(n), f"題目 {n}") for n in range(1, 11)]
    after = [question(str(n), f"題目 {n}" + ("!" if n <= 2 else "")) for n in range(1, 11)]
    assert compare_extractions(result(before), result(after)).agreement == pytest.approx(0.8)


def test_agreement_of_an_empty_comparison_is_one():
    assert compare_extractions(result([]), result([])).agreement == 1.0


# --- appearing and disappearing questions -----------------------------------

def test_added_and_removed_questions_are_listed():
    diff = compare_extractions(
        result([question("1", "x"), question("2", "y")]),
        result([question("1", "x"), question("3", "z")]),
    )
    assert diff.removed == ["2"]
    assert diff.added == ["3"]
    assert diff.identical == ["1"]
    assert not diff.is_clean


# --- other fields -----------------------------------------------------------

@pytest.mark.parametrize("before, after, expected", [
    (dict(marks=3.0), dict(marks=4.0), "marks"),
    (dict(tables=1), dict(tables=2), "table_regions"),
])
def test_other_field_changes_are_reported(before, after, expected):
    diff = compare_extractions(result([question("1", "x", **before)]),
                               result([question("1", "x", **after)]))
    assert [c.field for c in diff.changed[0].changes] == [expected]


# --- the text description ---------------------------------------------------

def test_no_change_describes_nothing():
    assert describe_text_change("abc", "abc") == ""


def test_pure_insertion_and_deletion():
    assert "{+xyz+}" in describe_text_change("abc", "abcxyz")
    assert "[-xyz-]" in describe_text_change("abcxyz", "abc")


def test_a_small_change_in_a_long_text_stays_short():
    before, after = "A" * 500 + "x" + "B" * 500, "A" * 500 + "y" + "B" * 500
    assert len(describe_text_change(before, after)) < 80


def test_render_lists_every_changed_question():
    diff = compare_extractions(
        result([question("1", "a"), question("2", "b")]),
        result([question("1", "a!"), question("2", "b!")]),
    )
    rendered = render_diff(diff, "run-a.json", "run-b.json")
    assert "run-a.json" in rendered and "run-b.json" in rendered
    assert "Agreement : 0%" in rendered
