"""Aggregate many extractions to see which kinds of question go wrong.

Reading one paper tells you whether that paper came out right. It does not tell
you that tables fail four times as often as prose, or that sub-questions are
where marks go missing. That only shows up across papers, grouped by what a
question actually contains.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

from app.extraction_repair import parent_id
from app.extraction_validator import _looks_like_a_table
from app.schemas import ExtractedQuestion, ExtractionResult


# What a question contains. A question can carry several of these at once, so
# the rates below overlap on purpose - that is what makes the comparison
# meaningful ("tables" versus "prose only", not a partition).
def question_features(question: ExtractedQuestion) -> set[str]:
    features = set()

    if question.table_regions or _looks_like_a_table(question.question_text):
        features.add("table")
    if question.question_type == "multiple_choice":
        features.add("multiple choice")
    if question.diagram_required:
        features.add("diagram")
    if parent_id(question.source_question_id):
        features.add("sub-question")
    if question.page_end > question.page_start:
        features.add("spans pages")
    if "\\(" in question.question_text or "$$" in question.question_text:
        features.add("latex")
    if question.marks is not None:
        features.add("own marks")
    elif question.group_marks is not None:
        features.add("group marks")
    else:
        features.add("no marks")
    if question.answer:
        features.add("printed answer")
    if not features & {"table", "diagram", "latex", "multiple choice"}:
        features.add("prose only")

    return features


@dataclass
class FeatureStats:
    name: str
    questions: int = 0
    flagged: int = 0
    codes: Counter = field(default_factory=Counter)

    @property
    def issue_rate(self) -> float:
        return self.flagged / self.questions if self.questions else 0.0


@dataclass
class PaperStats:
    file_name: str
    sha256: str
    model: str
    pages: int
    questions: int
    issues: int
    level: Optional[str] = None
    module: Optional[str] = None
    codes: Counter = field(default_factory=Counter)

    @property
    def questions_per_page(self) -> float:
        return self.questions / self.pages if self.pages else 0.0


@dataclass
class Analysis:
    papers: list[PaperStats] = field(default_factory=list)
    features: dict[str, FeatureStats] = field(default_factory=dict)
    issue_totals: Counter = field(default_factory=Counter)
    worst_questions: list[tuple[str, str, int]] = field(default_factory=list)

    @property
    def total_questions(self) -> int:
        return sum(p.questions for p in self.papers)

    @property
    def total_issues(self) -> int:
        return sum(p.issues for p in self.papers)

    def features_by_issue_rate(self) -> list[FeatureStats]:
        return sorted(self.features.values(),
                      key=lambda f: (-f.issue_rate, -f.questions, f.name))


def analyse(results: list[ExtractionResult]) -> Analysis:
    analysis = Analysis()

    for result in results:
        document = result.document
        by_question: dict[str, list] = {}
        for issue in result.issues:
            if issue.source_question_id:
                by_question.setdefault(issue.source_question_id, []).append(issue)

        analysis.papers.append(PaperStats(
            file_name=document.file_name,
            sha256=result.source.sha256 if result.source else "",
            model=result.run.model if result.run else "",
            pages=document.page_count,
            level=document.level,
            module=document.module,
            questions=len(document.questions),
            issues=len(result.issues),
            codes=Counter(i.issue_code for i in result.issues),
        ))
        analysis.issue_totals.update(i.issue_code for i in result.issues)

        for question in document.questions:
            issues = by_question.get(question.source_question_id, [])
            for name in question_features(question):
                stats = analysis.features.setdefault(name, FeatureStats(name))
                stats.questions += 1
                if issues:
                    stats.flagged += 1
                    stats.codes.update(i.issue_code for i in issues)

            if issues:
                analysis.worst_questions.append(
                    (document.file_name, question.source_question_id, len(issues)))

    analysis.worst_questions.sort(key=lambda row: -row[2])
    return analysis


def render_analysis(analysis: Analysis, top_questions: int = 15) -> str:
    lines = [
        "# Extraction analysis",
        "",
        "| | |",
        "|---|---|",
        f"| Papers | {len(analysis.papers)} |",
        f"| Questions | {analysis.total_questions} |",
        f"| Issues | {analysis.total_issues} |",
        "",
        "## By what the question contains",
        "",
        "A question counts under every feature it has, so these overlap.",
        "",
        "| Feature | Questions | Flagged | Rate | Most common issue |",
        "|---|---|---|---|---|",
    ]

    for stats in analysis.features_by_issue_rate():
        top = stats.codes.most_common(1)
        common = f"`{top[0][0]}` ({top[0][1]})" if top else ""
        lines.append(f"| {stats.name} | {stats.questions} | {stats.flagged} | "
                     f"{stats.issue_rate:.0%} | {common} |")

    lines += ["", "## Issues overall", "", "| Code | Count |", "|---|---|"]
    for code, count in analysis.issue_totals.most_common():
        lines.append(f"| `{code}` | {count} |")
    if not analysis.issue_totals:
        lines.append("| (none) | 0 |")

    lines += ["", "## By paper", "",
              "| Paper | Level | Module | Pages | Questions | Q/page | Issues |",
              "|---|---|---|---|---|---|---|"]
    for paper in sorted(analysis.papers, key=lambda p: -p.issues):
        lines.append(f"| {paper.file_name} | {paper.level or '?'} | "
                     f"{paper.module or '?'} | {paper.pages} | "
                     f"{paper.questions} | {paper.questions_per_page:.1f} | "
                     f"{paper.issues} |")

    if analysis.worst_questions:
        lines += ["", "## Questions with the most issues", "",
                  "| Paper | Question | Issues |", "|---|---|---|"]
        for file_name, question_id, count in analysis.worst_questions[:top_questions]:
            lines.append(f"| {file_name} | {question_id} | {count} |")

    return "\n".join(lines) + "\n"
