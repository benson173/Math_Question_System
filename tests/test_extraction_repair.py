"""Undoing a sub-question left in the stem its siblings share."""

from __future__ import annotations

import pytest

from app.extraction_repair import (
    common_prefix,
    find_stem_contamination,
    parent_id,
    repair_shared_stems,
    sibling_groups,
    trim_to_sentence_end,
)
from app.schemas import ExtractedDocument, ExtractedQuestion


# The stem as the model produced it: it ends with part (c)'s own question.
CONTAMINATED_STEM = (
    "圖中，O 是原點。L 是一條通過點 P(5, 3) 和點 Q(−1, −6) 的直線。"
    "L 分別與 x 軸和 y 軸相交於點 A 和點 B。求 △OAB 的面積。\n"
)
CLEAN_STEM = (
    "圖中，O 是原點。L 是一條通過點 P(5, 3) 和點 Q(−1, −6) 的直線。"
    "L 分別與 x 軸和 y 軸相交於點 A 和點 B。\n"
)
TAILS = ["求直線 L 的斜率。", "求 A 及 B 的坐標。", "求 △OAB 的面積。"]
IDS = ["19(a)", "19(b)", "19(c)"]


def question(question_id: str, text: str) -> ExtractedQuestion:
    return ExtractedQuestion(source_question_id=question_id, page_start=1,
                             page_end=1, question_text=text)


def document(questions) -> ExtractedDocument:
    return ExtractedDocument(file_name="s.pdf", page_count=12, questions=list(questions))


@pytest.fixture
def contaminated():
    return [question(i, CONTAMINATED_STEM + t) for i, t in zip(IDS, TAILS)]


@pytest.fixture
def clean():
    return [question(i, CLEAN_STEM + t) for i, t in zip(IDS, TAILS)]


# --- id parsing -------------------------------------------------------------

@pytest.mark.parametrize("question_id, expected", [
    ("19(a)", "19"), ("18(a)(ii)", "18(a)"), ("1(a)(i)", "1(a)"),
    ("12(b)", "12"), ("7", None), ("", None), ("(a)", None),
])
def test_parent_id(question_id, expected):
    assert parent_id(question_id) == expected


def test_a_lone_question_forms_no_group():
    assert sibling_groups([question("7", "x")]) == {}


def test_siblings_are_grouped_by_parent(contaminated):
    assert list(sibling_groups(contaminated)) == ["19"]


# --- detection --------------------------------------------------------------

def test_contamination_names_every_affected_sibling(contaminated):
    found = find_stem_contamination(contaminated)
    assert len(found) == 1
    assert found[0].question_ids == IDS
    assert found[0].removed == "求 △OAB 的面積"
    assert found[0].owner == "19(c)"


def test_a_clean_group_is_left_alone(clean):
    assert find_stem_contamination(clean) == []


# --- repair -----------------------------------------------------------------

def test_repair_reproduces_the_correct_text(contaminated, clean):
    doc = document(contaminated)
    repair_shared_stems(doc)
    assert [q.question_text for q in doc.questions] == \
           [q.question_text.strip() for q in clean]


def test_repair_records_what_it_changed(contaminated):
    doc = document(contaminated)
    repair_shared_stems(doc)
    for q in doc.questions:
        assert len(q.extraction_notes) == 1
        assert "求 △OAB 的面積" in q.extraction_notes[0]
        assert "19(c)" in q.extraction_notes[0]


def test_repair_leaves_the_owner_stating_its_question_once(contaminated):
    doc = document(contaminated)
    repair_shared_stems(doc)
    owner = next(q for q in doc.questions if q.source_question_id == "19(c)")
    assert owner.question_text.count("求 △OAB 的面積") == 1


def test_repairing_clean_text_changes_nothing(clean):
    doc = document(clean)
    before = [q.question_text for q in doc.questions]
    assert repair_shared_stems(doc) == []
    assert [q.question_text for q in doc.questions] == before
    assert all(not q.extraction_notes for q in doc.questions)


def test_repair_is_idempotent(contaminated):
    doc = document(contaminated)
    repair_shared_stems(doc)
    once = [q.question_text for q in doc.questions]
    assert repair_shared_stems(doc) == []
    assert [q.question_text for q in doc.questions] == once


# --- groups that must not be touched ----------------------------------------

@pytest.mark.parametrize("questions", [
    # Shared stem ends with an instruction, not with any part's question.
    [("11(a)", "某筆盒內有 6 支藍色筆。求下列各事件的概率。\n抽出的筆是藍色或黑色。"),
     ("11(b)", "某筆盒內有 6 支藍色筆。求下列各事件的概率。\n抽出的筆不是紅色。")],
    # Stem is context only.
    [("5(a)", "某盒朱古力的成本為 $70。虧蝕百分率為 20%。\n求該盒朱古力的售價。"),
     ("5(b)", "某盒朱古力的成本為 $70。虧蝕百分率為 20%。\n求該盒朱古力的標價。")],
    # Stem has no sentence terminator at all.
    [("2(a)", "因式分解\n7r − 21s"), ("2(b)", "因式分解\nr² + 2rs − 15s²")],
    # Deeper parts.
    [("18(a)(i)", "下表顯示分數的分佈。已知 k 為一正整數。\n求 k 的最小可取值；"),
     ("18(a)(ii)", "下表顯示分數的分佈。已知 k 為一正整數。\n求 k 的最大可取值。")],
])
def test_legitimate_shared_stems_survive(questions):
    doc = document(question(i, t) for i, t in questions)
    before = [q.question_text for q in doc.questions]
    assert repair_shared_stems(doc) == []
    assert [q.question_text for q in doc.questions] == before


def test_a_single_sentence_stem_is_never_stripped():
    # Removing it would delete the stem entirely.
    questions = [question("3(a)", "求 x 的值。"),
                 question("3(b)", "求 x 的值。\n求 y 的值。")]
    assert find_stem_contamination(questions) == []


def test_a_very_short_sentence_is_ignored():
    questions = [question("4(a)", "計算。求 x。"), question("4(b)", "計算。求 x。\n求 y。")]
    assert find_stem_contamination(questions) == []


# --- helpers ----------------------------------------------------------------

def test_common_prefix():
    assert common_prefix([]) == ""
    assert common_prefix(["abc"]) == "abc"
    assert common_prefix(["abcd", "abce"]) == "abc"
    assert common_prefix(["abc", "xyz"]) == ""


def test_trim_to_sentence_end():
    assert trim_to_sentence_end("一句。兩句。剩低") == "一句。兩句。"
    assert trim_to_sentence_end("冇句號") == ""
