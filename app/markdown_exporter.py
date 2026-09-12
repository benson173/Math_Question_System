"""Write an extraction as a readable Markdown report.

The JSON is what later stages read; this is what a person reads. Question text
is copied verbatim - it is already Markdown, so printed tables render as
tables - and rendered diagrams are linked relative to the report, so the file
stays valid if the whole data/ folder moves.
"""

from __future__ import annotations

import os
from pathlib import Path

from app.schemas import DiagramAsset, ExtractedQuestion, ExtractionResult, ValidationIssue


SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def markdown_output_path(json_path: str | Path) -> Path:
    """The report sits beside the JSON, same name, .md instead."""
    return Path(json_path).with_suffix(".md")


def _marks_label(marks: float) -> str:
    value = int(marks) if float(marks).is_integer() else marks
    return f"{value} mark" if value == 1 else f"{value} marks"


def _pages(question: ExtractedQuestion) -> str:
    if question.page_start == question.page_end:
        return f"page {question.page_start}"
    return f"pages {question.page_start}–{question.page_end}"


def _relative_link(image_path: str, report_path: Path) -> str:
    """Path from the report to the image, so the link survives a move."""
    try:
        return os.path.relpath(Path(image_path).resolve(), report_path.parent.resolve())
    except ValueError:
        # Different drives on Windows - an absolute path is the best we can do.
        return str(image_path)


def _summary_table(result: ExtractionResult) -> list[str]:
    document, source, run = result.document, result.source, result.run
    rows = [
        ("PDF", document.file_name),
        ("Pages", str(document.page_count)),
        ("Questions", str(len(document.questions))),
    ]
    if source:
        rows.append(("SHA256", f"`{source.sha256}`"))
        rows.append(("Size", f"{source.byte_size:,} bytes"))
    if run:
        rows.append(("Extracted", run.extracted_at))
        rows.append(("Model", run.model))
        rows.append(("Run", f"`{run.run_id}`"))
        rows.append(("Versions", f"{run.extraction_version} / {run.question_object_version}"))
    if result.diagrams:
        cropped = sum(1 for d in result.diagrams if d.cropped)
        rows.append(("Diagrams", f"{len(result.diagrams)} "
                                 f"({cropped} cropped, {len(result.diagrams) - cropped} full page)"))

    lines = ["| | |", "|---|---|"]
    lines += [f"| {label} | {value} |" for label, value in rows]
    return lines


def _issue_summary(issues: list[ValidationIssue]) -> str:
    if not issues:
        return "**Issues:** none"
    counts: dict[str, int] = {}
    for issue in issues:
        counts[issue.severity] = counts.get(issue.severity, 0) + 1
    parts = [f"{counts[s]} {s}" for s in sorted(counts, key=lambda s: SEVERITY_ORDER.get(s, 9))]
    return f"**Issues:** {' · '.join(parts)}"


def _question_section(
    question: ExtractedQuestion,
    asset: DiagramAsset | None,
    report_path: Path,
) -> list[str]:
    labels = []
    if question.marks is not None:
        labels.append(_marks_label(question.marks))
    elif question.group_marks is not None:
        scope = question.group_marks_scope or "the group"
        labels.append(f"{_marks_label(question.group_marks)} for {scope}")
    if question.diagram_required:
        labels.append("diagram")

    lines = [f"## {question.source_question_id}", ""]
    meta = _pages(question)
    if labels:
        meta += " · " + " · ".join(labels)
    lines += [f"*{meta}*", "", question.question_text, ""]

    if asset:
        link = _relative_link(asset.image_path, report_path)
        kind = "cropped" if asset.cropped else "full page"
        lines += [
            f"![{question.source_question_id}]({link})",
            "",
            f"*{kind} · {asset.width}×{asset.height} · page {asset.page}*",
            "",
        ]
    elif question.diagram_required:
        lines += ["> ⚠️ Needs a diagram, but no image was rendered.", ""]

    if question.answer:
        lines += [f"**Answer:** {question.answer}", ""]
    if question.worked_solution:
        lines += ["**Worked solution:**", "", question.worked_solution, ""]
    for note in question.extraction_notes:
        lines += [f"> 📝 {note}", ""]

    return lines


def render_markdown(result: ExtractionResult, report_path: Path) -> str:
    document = result.document
    assets = {asset.source_question_id: asset for asset in result.diagrams}

    lines = [f"# {document.file_name}", ""]
    lines += _summary_table(result)
    lines += ["", _issue_summary(result.issues), "", "---", ""]

    for question in document.questions:
        lines += _question_section(question, assets.get(question.source_question_id), report_path)
        lines += ["---", ""]

    lines += ["## Validation issues", ""]
    if not result.issues:
        lines += ["None.", ""]
    else:
        lines += ["| Severity | Code | Question | Message |", "|---|---|---|---|"]
        ordered = sorted(result.issues, key=lambda i: SEVERITY_ORDER.get(i.severity, 9))
        for issue in ordered:
            where = issue.source_question_id or ""
            message = issue.message.replace("|", "\\|")
            lines.append(f"| {issue.severity} | `{issue.issue_code}` | {where} | {message} |")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def export_extraction_markdown(result: ExtractionResult, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown(result, path), encoding="utf-8")
    return path
