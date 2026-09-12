"""Grouping questions by what they contain, to see which kinds go wrong."""

from __future__ import annotations

import pytest

from app.extraction_stats import analyse, question_features, render_analysis
from app.extraction_validator import validate_extraction
from app.schemas import (
    ExtractedDocument,
    ExtractedQuestion,
    ExtractionResult,
    ExtractionRun,
    PageRegion,
    SourceDocument,
    ValidationIssue,
)


TABLE = "\n\n| 球 | 現金獎 |\n| --- | --- |\n| 黑色 | $22 |\n"
BROKEN_TABLE = "\n\n球 | 現金獎\n黑色 | $22\n白色 | $0\n"


def region() -> PageRegion:
    return PageRegion(page=1, y_min=100, x_min=100, y_max=600, x_max=900)


def question(question_id="1", text="求 x 的值。", **overrides) -> ExtractedQuestion:
    defaults = dict(source_question_id=question_id, page_start=1, page_end=1,
                    question_text=text)
    defaults.update(overrides)
    return ExtractedQuestion(**defaults)


def result(questions, file_name="p.pdf", pages=1, issues=None) -> ExtractionResult:
    document = ExtractedDocument(level="F4", file_name=file_name, page_count=pages,
                                 questions=list(questions))
    return ExtractionResult(
        document=document,
        issues=validate_extraction(document) if issues is None else issues,
        source=SourceDocument(file_name=file_name, sha256="a" * 64,
                              page_count=pages, byte_size=1),
        run=ExtractionRun(run_id="r", extracted_at="t", extraction_version="QEE_v1",
                          question_object_version="QOS_v1", model="m"),
    )


# --- features ---------------------------------------------------------------

@pytest.mark.parametrize("kwargs, expected", [
    (dict(text="求 x。" + TABLE), "table"),
    (dict(table_regions=[region()]), "table"),
    (dict(diagram_required=True), "diagram"),
    (dict(question_id="2(a)"), "sub-question"),
    (dict(page_start=4, page_end=5), "spans pages"),
    (dict(text=r"化簡 \(\frac{a}{b}\)。"), "latex"),
    (dict(marks=3), "own marks"),
    (dict(group_marks=4), "group marks"),
    (dict(answer="42"), "printed answer"),
])
def test_feature_detection(kwargs, expected):
    question_id = kwargs.pop("question_id", "1")
    text = kwargs.pop("text", "求 x 的值。")
    assert expected in question_features(question(question_id, text, **kwargs))


def test_a_plain_question_is_prose_only():
    assert "prose only" in question_features(question())


def test_a_question_with_a_table_is_not_prose_only():
    assert "prose only" not in question_features(question(text="求 x。" + TABLE))


def test_a_question_with_neither_kind_of_mark_is_counted():
    features = question_features(question())
    assert "no marks" in features
    assert "own marks" not in features and "group marks" not in features


def test_own_marks_win_over_group_marks():
    features = question_features(question(marks=2, group_marks=4))
    assert "own marks" in features and "group marks" not in features


def test_features_overlap_on_purpose():
    features = question_features(
        question("2(a)", "求 x。" + TABLE, diagram_required=True, marks=3))
    assert {"table", "diagram", "sub-question", "own marks"} <= features


# --- aggregation ------------------------------------------------------------

def test_totals_add_up():
    analysis = analyse([
        result([question("1"), question("2")], file_name="a.pdf"),
        result([question("1")], file_name="b.pdf"),
    ])
    assert len(analysis.papers) == 2
    assert analysis.total_questions == 3


def test_a_feature_rate_reflects_only_flagged_questions():
    # Two tables, one of them broken.
    analysis = analyse([result([
        question("1", "求 x。" + TABLE, table_regions=[region()], marks=3),
        question("2", "求 y。" + BROKEN_TABLE, table_regions=[region()], marks=3),
    ])])
    tables = analysis.features["table"]
    assert tables.questions == 2
    assert tables.flagged == 1
    assert tables.issue_rate == pytest.approx(0.5)


def test_a_clean_paper_has_no_flagged_features():
    analysis = analyse([result([question("1", marks=3), question("2", marks=3)])])
    assert all(stats.flagged == 0 for stats in analysis.features.values())
    assert analysis.total_issues == 0


def test_features_are_ordered_by_issue_rate():
    analysis = analyse([result([
        question("1", "求 x。" + BROKEN_TABLE, marks=3),
        question("2", marks=3),
        question("3", marks=3),
    ])])
    ordered = analysis.features_by_issue_rate()
    assert ordered[0].name == "table"
    assert ordered[0].issue_rate > ordered[-1].issue_rate


def test_document_level_issues_are_counted_but_not_blamed_on_a_question():
    issues = [ValidationIssue(issue_code="SUSPICIOUSLY_FEW_QUESTIONS",
                              severity="medium", message="m")]
    analysis = analyse([result([question("1", marks=3)], issues=issues)])
    assert analysis.issue_totals["SUSPICIOUSLY_FEW_QUESTIONS"] == 1
    assert all(stats.flagged == 0 for stats in analysis.features.values())


def test_worst_questions_come_first():
    analysis = analyse([result([
        question("1", "求 x。" + BROKEN_TABLE),   # malformed table + no marks
        question("2", marks=3),
    ])])
    assert analysis.worst_questions[0][1] == "1"


def test_questions_per_page():
    analysis = analyse([result([question(str(n)) for n in range(1, 7)], pages=12)])  # noqa: E501
    assert analysis.papers[0].questions_per_page == pytest.approx(0.5)


def test_zero_pages_does_not_divide_by_zero():
    analysis = analyse([result([question("1")], pages=0)])
    assert analysis.papers[0].questions_per_page == 0.0


# --- rendering --------------------------------------------------------------

def test_report_covers_each_section():
    analysis = analyse([result([question("1", "求 x。" + BROKEN_TABLE, marks=3)])])
    report = render_analysis(analysis)
    for heading in ("# Extraction analysis", "## By what the question contains",
                    "## Issues overall", "## By paper"):
        assert heading in report
    assert "`MALFORMED_TABLE`" in report


def test_a_clean_run_still_renders():
    report = render_analysis(analyse([result([question("1", marks=3)])]))
    assert "| (none) | 0 |" in report


def test_an_empty_analysis_renders():
    assert "# Extraction analysis" in render_analysis(analyse([]))
