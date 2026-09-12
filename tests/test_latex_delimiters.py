"""LaTeX that renders nowhere, and a paper that spells its minus sign three ways."""

from __future__ import annotations

import pytest

from app.extraction_validator import (
    count_dashes,
    find_undelimited_latex,
    validate_extraction,
)
from app.schemas import ExtractedDocument, ExtractedQuestion


def question(question_id, text) -> ExtractedQuestion:
    return ExtractedQuestion(source_question_id=question_id, page_start=1,
                             page_end=1, question_text=text)


def codes(questions) -> list[str]:
    document = ExtractedDocument(level="F4", file_name="s.pdf", page_count=1,
                                 questions=list(questions))
    return sorted({issue.issue_code for issue in validate_extraction(document)})


# --- LaTeX outside its delimiters -------------------------------------------

@pytest.mark.parametrize("text, expected", [
    (r"L = 10 \log \frac{I}{10^{-12}}", {"\\log", "\\frac", "^{-12}"}),
    (r"把 y = \log_a bx 的圖像記為 G。", {"\\log"}),
    (r"簡化 i^{1029} - i^{1026}。", {"^{1029}", "^{1026}"}),
])
def test_undelimited_latex_is_found(text, expected):
    assert set(find_undelimited_latex(text)) == expected


@pytest.mark.parametrize("text", [
    r"以 cos θ 表示 \(\frac{\tan \theta - \sin \theta}{\tan \theta + \sin \theta}\)。",
    r"Q(m) = \(2Ar^{\frac{n}{2}}\)",
    r"化簡 \(\frac{(x^3 y^8)^8}{x^{-4} y^6}\)，並以正指數表示答案。",
    r"考慮：\(\begin{cases} x + 2y \le 40 \\ x + y \ge 26 \end{cases}\)",
    "化簡 (x⁵ y⁶)(x⁻³ y³)⁷，並以正指數表示答案。",
    "A 與 J 之間的最短距離是 √137。",
    "解一元二次方程 x² − 6x − 4 = 0。",
    "某農場有若干隻雞和牛。",
    "求平均數。\n\n| 分數 | 0 | 1 |\n| --- | --- | --- |\n| 人數 | 14 | 9 |",
])
def test_correct_maths_is_never_flagged(text):
    assert find_undelimited_latex(text) == []


def test_the_issue_lists_what_it_found():
    issues = [i for i in validate_extraction(ExtractedDocument(level="F4",
        file_name="s.pdf", page_count=1,
        questions=[question("18(a)", r"L = 10 \log \frac{I}{10^{-12}}")]))
        if i.issue_code == "LATEX_NOT_DELIMITED"]
    assert len(issues) == 1
    assert issues[0].severity == "medium"
    assert "\\log" in issues[0].message or "\\frac" in issues[0].message


# --- one paper, three dashes ------------------------------------------------

MIXED_PAPER = [
    question("10", "解一元二次方程 x - 6x² - 4 = 0。"),
    question("12", "若 k 使得 kx² – kx + k – 2 = 0 有二重實根，求 k。"),
    question("13", "L₁ 的方程為 x – 2y + 5 = 0。"),
    question("14", "已知 L₁ : 2x + 3y - 12 = 0 及 L₂ : 3x - 2y + 6 = 0。"),
    question("19", "已知 α 和 β 為方程 2x² + 8x − 3 = 0 的兩根。"),
    question("4(a)", "因式分解 9a² − 25"),
    # A third U+2212: below MIN_DASH_USES a character is treated as a stray,
    # so a paper that really mixes three needs three uses of each.
    question("20", "求 5 − 2 的值。"),
]


def test_a_paper_mixing_dashes_is_reported():
    assert "INCONSISTENT_MINUS_SIGN" in codes(MIXED_PAPER)


def test_it_is_only_informational():
    issue = next(i for i in validate_extraction(
        ExtractedDocument(level="F4", file_name="s.pdf", page_count=1, questions=MIXED_PAPER))
        if i.issue_code == "INCONSISTENT_MINUS_SIGN")
    assert issue.severity == "low"
    assert "3 different dash characters" in issue.message


@pytest.mark.parametrize("dash", ["-", "–", "−"])
def test_a_paper_using_one_dash_is_clean(dash):
    questions = [question(str(n), f"方程 {n}x² {dash} {n}x {dash} 1 = 0 的根。")
                 for n in range(1, 6)]
    assert "INCONSISTENT_MINUS_SIGN" not in codes(questions)


def test_a_couple_of_stray_dashes_do_not_trigger_it():
    assert "INCONSISTENT_MINUS_SIGN" not in codes([question("1", "a-b 同 c–d")])


@pytest.mark.parametrize("text, expected", [
    ("x - 6x² - 4 = 0", {"-": 2}),
    ("2x² + 8x − 3 = 0", {"−": 1}),
    ("求 x 的值。", {}),
    # A hyphen inside \( \) is the LaTeX minus and is not a prose dash.
    (r"化簡 \( \frac{6}{2x + 5} - \frac{3}{x - 4} \)。", {}),
    (r"若聲音強度為 \( 10^{-7.2} \) 單位，求 L − 3。", {"−": 1}),
])
def test_count_dashes(text, expected):
    assert count_dashes(text) == expected


# The only issue three otherwise-clean papers reported, traced to hyphens that
# were all inside formulas. Each line is copied from those papers as extracted.
CLEAN_PAPER = [
    question("9", r"已知 θ 是銳角，以 cos θ 表示 \( \frac{\tan\theta - \sin\theta}{\tan\theta + \sin\theta} \)。"),
    question("18", r"L = \( 10\log\frac{I}{10^{-12}} \)" "\n" r"若聲音強度為 \( 10^{-7.2} \) 單位。"),
    question("2", r"化簡 \( \frac{6}{2x + 5} - \frac{3}{x - 4} \)。"),
    question("11", r"\( 4 - x < \frac{5 - 2x}{3} \) 及 \( 18 + x > 4 \) …… (*)"),
    question("36", r"\( \begin{cases} x + 2y \le 40 \\ y \ge x - 10 \end{cases} \)"),
    question("3", "9u² − 4v² + 10v − 15u ="),
    question("7", "設 f(x) = 2x² − 3x + 1。則 f(α) − f(2 − α) ="),
    question("9b", "3x − 5 ≤ 10 − 2x < 18 的解為"),
]


def test_hyphens_inside_formulas_do_not_make_a_paper_inconsistent():
    assert "INCONSISTENT_MINUS_SIGN" not in codes(CLEAN_PAPER)
