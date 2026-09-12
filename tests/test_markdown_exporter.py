"""The Markdown report: structure, verbatim content, and image links."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.markdown_exporter import (
    export_extraction_markdown,
    markdown_output_path,
    render_markdown,
)
from app.schemas import RenderedImage, ValidationIssue


@pytest.fixture
def report_path(tmp_path):
    return tmp_path / "extracted" / "paper-abc123.md"


def test_output_path_sits_beside_the_json():
    assert markdown_output_path("data/extracted/x-abc.json").name == "x-abc.md"
    assert markdown_output_path(Path("/a/b/x-abc.json")) == Path("/a/b/x-abc.md")


def test_report_opens_with_the_file_name(make_result, report_path):
    assert render_markdown(make_result(), report_path).startswith("# sample.pdf\n")


def test_summary_carries_provenance(make_result, report_path):
    text = render_markdown(make_result(), report_path)
    assert "a" * 64 in text
    assert "QEE_v1 / QOS_v1" in text
    assert "test-model" in text


def test_question_text_is_copied_verbatim(make_result, make_document, make_question, report_path):
    original = ("在某次大抽獎中…\n\n| 球 | 現金獎 |\n| :---: | :---: |\n"
                "| 黑色 | $22 |\n\n(a) 求隨機抽取一次的期望現金獎。")
    document = make_document([make_question(source_question_id="17(a)",
                                            question_text=original)])
    assert original in render_markdown(make_result(document=document), report_path)


def test_math_symbols_survive(make_result, make_document, make_question, report_path):
    document = make_document([make_question(question_text="1 − 225x² ÷ ½π ≤ 3")])
    assert "1 − 225x² ÷ ½π ≤ 3" in render_markdown(make_result(document=document), report_path)


def test_sub_question_ids_become_headings(make_result, make_document, make_question, report_path):
    document = make_document([
        make_question(source_question_id="17(a)"),
        make_question(source_question_id="17(b)"),
    ])
    text = render_markdown(make_result(document=document), report_path)
    assert "## 17(a)" in text and "## 17(b)" in text


@pytest.mark.parametrize("marks, expected", [
    (1, "1 mark"), (1.0, "1 mark"), (2, "2 marks"), (4.0, "4 marks"), (2.5, "2.5 marks"),
])
def test_marks_are_written_naturally(make_result, make_document, make_question,
                                     report_path, marks, expected):
    document = make_document([make_question(marks=marks)])
    assert f"· {expected}" in render_markdown(make_result(document=document), report_path)


def test_group_marks_are_shown_with_their_scope(
    make_result, make_document, make_question, report_path
):
    document = make_document([make_question(group_marks=4, group_marks_scope="12(b)-(d)")])
    text = render_markdown(make_result(document=document), report_path)
    assert "· 4 marks for 12(b)-(d)" in text


def test_own_marks_win_over_group_marks(make_result, make_document, make_question, report_path):
    document = make_document([make_question(marks=2, group_marks=4, group_marks_scope="12")])
    text = render_markdown(make_result(document=document), report_path)
    assert "· 2 marks" in text and "for 12" not in text


def test_single_and_multi_page_questions_read_correctly(
    make_result, make_document, make_question, report_path
):
    one = make_document([make_question(page_start=9, page_end=9)], page_count=9)
    assert "*page 9" in render_markdown(make_result(document=one), report_path)

    spread = make_document([make_question(page_start=4, page_end=5)], page_count=9)
    assert "*pages 4–5" in render_markdown(make_result(document=spread), report_path)


# --- diagrams ---------------------------------------------------------------

def diagram_result(make_result, make_document, make_question, tmp_path, **asset_kwargs):
    document = make_document([make_question(source_question_id="16", diagram_required=True)])
    result = make_result(document=document)
    defaults = dict(source_question_id="16", kind="diagram", index=0, page=8,
                    image_path=str(tmp_path / "diagrams" / "paper-abc123" / "16.png"),
                    cropped=True, width=842, height=617)
    defaults.update(asset_kwargs)
    result.diagrams = [RenderedImage(**defaults)]
    return result


def test_diagram_is_linked_relative_to_the_report(
    make_result, make_document, make_question, tmp_path, report_path
):
    result = diagram_result(make_result, make_document, make_question, tmp_path)
    text = render_markdown(result, report_path)
    # The report is in extracted/, the image in diagrams/ - one level up and over.
    assert "![16](../diagrams/paper-abc123/16.png)" in text


def test_diagram_caption_says_how_it_was_produced(
    make_result, make_document, make_question, tmp_path, report_path
):
    cropped = diagram_result(make_result, make_document, make_question, tmp_path)
    assert "*cropped · 842×617 · page 8*" in render_markdown(cropped, report_path)

    full = diagram_result(make_result, make_document, make_question, tmp_path, cropped=False)
    assert "*full page · 842×617 · page 8*" in render_markdown(full, report_path)


def test_missing_diagram_is_called_out(make_result, make_document, make_question, report_path):
    document = make_document([make_question(diagram_required=True)])
    text = render_markdown(make_result(document=document), report_path)
    assert "no image was rendered" in text


def test_questions_without_diagrams_get_no_warning(make_result, report_path):
    assert "no image was rendered" not in render_markdown(make_result(), report_path)


# --- issues -----------------------------------------------------------------

def test_no_issues_reads_cleanly(make_result, report_path):
    text = render_markdown(make_result(), report_path)
    assert "**Issues:** none" in text
    assert "None." in text


def test_issues_are_counted_and_tabulated(make_result, report_path):
    result = make_result(issues=[
        ValidationIssue(issue_code="LOW_ONE", severity="low", message="a"),
        ValidationIssue(issue_code="CRIT", severity="critical", message="b"),
        ValidationIssue(issue_code="MED", severity="medium", message="c", source_question_id="17(a)"),
    ])
    text = render_markdown(result, report_path)
    assert "**Issues:** 1 critical · 1 medium · 1 low" in text
    # Most severe first in the table.
    assert text.index("`CRIT`") < text.index("`MED`") < text.index("`LOW_ONE`")
    assert "| 17(a) |" in text


def test_pipe_in_a_message_does_not_break_the_table(make_result, report_path):
    result = make_result(issues=[
        ValidationIssue(issue_code="X", severity="low", message="a | b | c"),
    ])
    assert r"a \| b \| c" in render_markdown(result, report_path)


# --- writing ----------------------------------------------------------------

def test_export_creates_parent_directories(make_result, tmp_path):
    path = export_extraction_markdown(make_result(), tmp_path / "deep" / "nested" / "r.md")
    assert path.exists()
    assert path.read_text(encoding="utf-8").startswith("# sample.pdf")


def test_export_ends_with_exactly_one_newline(make_result, tmp_path):
    path = export_extraction_markdown(make_result(), tmp_path / "r.md")
    text = path.read_text(encoding="utf-8")
    assert text.endswith("\n") and not text.endswith("\n\n")
