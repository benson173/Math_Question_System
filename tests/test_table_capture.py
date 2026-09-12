"""Capturing a picture of every printed table, alongside its transcription."""

from __future__ import annotations

import pytest

from app.diagram_geometry import page_index_for
from app.diagram_renderer import asset_file_name, planned_images
from app.extraction_validator import has_blocking_issues, validate_extraction
from app.schemas import ExtractedDocument, ExtractedQuestion, PageRegion


GOOD_TABLE = "題幹。\n\n| 球 | 現金獎 |\n| --- | --- |\n| 黑色 | $22 |\n\n求期望值。"
BAD_TABLE = "題幹。\n\n球 | 現金獎\n黑色 | $22\n白色 | $0\n\n求期望值。"
RAGGED_TABLE = ("題幹。\n\n| | | 第二枚 | | | | |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| | | 1 | 2 | 3 | 4 | 5 | 6 |\n"
                "| 第一枚 | 1 | (1,1) | | | | | |\n")
PROSE = "圖中，O 是 △ABC 的外心。求 OA。"


def region(page=1, y_min=200, x_min=100, y_max=600, x_max=900) -> PageRegion:
    return PageRegion(page=page, y_min=y_min, x_min=x_min, y_max=y_max, x_max=x_max)


def question(question_id, text=PROSE, *, diagram=False, diagram_region=None,
             table_regions=None, page=1) -> ExtractedQuestion:
    return ExtractedQuestion(
        source_question_id=question_id, page_start=page, page_end=page,
        question_text=text, diagram_required=diagram, diagram_region=diagram_region,
        table_regions=table_regions or [],
    )


def document(questions, page_count=12) -> ExtractedDocument:
    return ExtractedDocument(file_name="s.pdf", page_count=page_count,
                             questions=list(questions))


def severities(text, table_regions) -> dict[str, str]:
    doc = document([question("1", text, table_regions=table_regions)], page_count=1)
    return {i.issue_code: i.severity for i in validate_extraction(doc)}


# --- what gets rendered -----------------------------------------------------

def test_diagrams_and_tables_are_both_planned():
    doc = document([
        question("16", diagram=True, diagram_region=region(page=8)),
        question("17(a)", GOOD_TABLE, table_regions=[region(page=9)]),
        question("9"),
    ])
    plan = [(q.source_question_id, kind, index) for q, kind, index, _ in planned_images(doc)]
    assert plan == [("16", "diagram", 0), ("17(a)", "table", 0)]


def test_a_question_with_two_tables_plans_both():
    doc = document([question("15(a)", GOOD_TABLE,
                             table_regions=[region(page=7), region(page=7, y_min=650)])])
    assert [index for _, _, index, _ in planned_images(doc)] == [0, 1]


def test_a_question_needing_nothing_plans_nothing():
    assert planned_images(document([question("9")])) == []


# --- file names -------------------------------------------------------------

@pytest.mark.parametrize("question_id, kind, index, expected", [
    ("16", "diagram", 0, "16.png"),
    ("17(a)", "table", 0, "17-a-table-1.png"),
    ("15(a)", "table", 1, "15-a-table-2.png"),
    ("18(a)(i)", "table", 0, "18-a-i-table-1.png"),
])
def test_asset_file_name(question_id, kind, index, expected):
    assert asset_file_name(question_id, kind, index) == expected


def test_a_diagram_and_a_table_of_one_question_do_not_collide():
    assert asset_file_name("16", "diagram", 0) != asset_file_name("16", "table", 0)


# --- page selection ---------------------------------------------------------

def test_a_table_uses_its_own_page_not_the_diagram_s():
    q = question("15(a)", GOOD_TABLE, diagram=True, diagram_region=region(page=3),
                 table_regions=[region(page=7)], page=7)
    assert page_index_for(q, 12) == 2                       # the diagram
    assert page_index_for(q, 12, q.table_regions[0]) == 6    # the table


# --- severity depends on whether a picture exists ---------------------------

@pytest.mark.parametrize("text, code", [
    (BAD_TABLE, "MALFORMED_TABLE"),
    (RAGGED_TABLE, "RAGGED_TABLE"),
])
def test_a_broken_table_is_softened_when_a_picture_was_captured(text, code):
    assert severities(text, [])[code] == "medium"
    assert severities(text, [region()])[code] == "low"


def test_the_message_says_a_picture_exists():
    doc = document([question("1", BAD_TABLE, table_regions=[region()])], page_count=1)
    message = next(i.message for i in validate_extraction(doc)
                   if i.issue_code == "MALFORMED_TABLE")
    assert "picture of the table was captured" in message


def test_an_unusable_region_does_not_count_as_a_picture():
    unusable = region(x_min=900, x_max=100)
    assert severities(BAD_TABLE, [unusable])["MALFORMED_TABLE"] == "medium"


# --- a table with no picture ------------------------------------------------

def test_a_transcribed_table_with_no_region_is_noted():
    assert severities(GOOD_TABLE, [])["TABLE_NOT_CAPTURED"] == "low"


def test_a_captured_table_is_not_noted():
    assert "TABLE_NOT_CAPTURED" not in severities(GOOD_TABLE, [region()])


def test_prose_is_never_asked_for_a_table_picture():
    assert "TABLE_NOT_CAPTURED" not in severities(PROSE, [])


# --- nothing about tables fails an ingestion --------------------------------

def test_table_problems_never_block():
    doc = document([question("1", BAD_TABLE), question("2", RAGGED_TABLE)], page_count=1)
    assert has_blocking_issues(validate_extraction(doc)) is False
