"""Compare two extractions of the same PDF.

Across four runs of one paper the model produced a table without a separator
row, then with one; a stem carrying a sibling's question, then not; a minus
sign as U+2212, then as an en dash; and once a sentence with words that are not
on the page, accompanied by a note asserting they are. No check on a single run
can see any of that, because each run looks internally consistent.

Comparing two runs can. Where they agree, the text is very likely what the page
says. Where they disagree, one of them is wrong and a person should look.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import difflib

from app.schemas import ExtractedQuestion, ExtractionResult


# Fields worth comparing, in the order they are reported.
COMPARED_FIELDS = (
    "question_text",
    "marks",
    "group_marks",
    "group_marks_scope",
    "page_start",
    "page_end",
    "answer",
    "worked_solution",
    "diagram_required",
)

CONTEXT_CHARS = 10


@dataclass
class FieldChange:
    field: str
    before: str
    after: str
    detail: str = ""


@dataclass
class QuestionDiff:
    source_question_id: str
    changes: list[FieldChange] = field(default_factory=list)


@dataclass
class ExtractionDiff:
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    changed: list[QuestionDiff] = field(default_factory=list)
    identical: list[str] = field(default_factory=list)

    @property
    def total_compared(self) -> int:
        return len(self.identical) + len(self.changed)

    @property
    def agreement(self) -> float:
        """Share of shared questions that came out identical."""
        if not self.total_compared:
            return 1.0
        return len(self.identical) / self.total_compared

    @property
    def is_clean(self) -> bool:
        return not (self.added or self.removed or self.changed)


def describe_text_change(before: str, after: str, context: int = CONTEXT_CHARS) -> str:
    """Show only what moved, with a little text either side.

    Removals read as [-old-] and additions as {+new+}, so a change is legible
    without printing two long questions in full.
    """
    matcher = difflib.SequenceMatcher(None, before, after, autojunk=False)
    pieces: list[str] = []
    previous_end = 0

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        lead = before[max(previous_end, i1 - context):i1]
        if i1 - context > previous_end:
            lead = "…" + lead
        pieces.append(lead)
        if tag in ("replace", "delete"):
            pieces.append(f"[-{before[i1:i2]}-]")
        if tag in ("replace", "insert"):
            pieces.append(f"{{+{after[j1:j2]}+}}")
        trail = before[i2:i2 + context]
        pieces.append(trail + ("…" if i2 + context < len(before) else ""))
        previous_end = i2 + context

    return "".join(pieces) if pieces else ""


def _format(value) -> str:
    return "" if value is None else str(value)


def compare_questions(before: ExtractedQuestion, after: ExtractedQuestion) -> QuestionDiff:
    diff = QuestionDiff(source_question_id=before.source_question_id)

    for name in COMPARED_FIELDS:
        old, new = getattr(before, name), getattr(after, name)
        if old == new:
            continue
        change = FieldChange(field=name, before=_format(old), after=_format(new))
        if name == "question_text":
            change.detail = describe_text_change(_format(old), _format(new))
        diff.changes.append(change)

    if len(before.table_regions) != len(after.table_regions):
        diff.changes.append(FieldChange(
            field="table_regions",
            before=str(len(before.table_regions)),
            after=str(len(after.table_regions)),
        ))

    return diff


def compare_extractions(before: ExtractionResult, after: ExtractionResult) -> ExtractionDiff:
    old = {q.source_question_id: q for q in before.document.questions}
    new = {q.source_question_id: q for q in after.document.questions}

    diff = ExtractionDiff(
        added=sorted(set(new) - set(old)),
        removed=sorted(set(old) - set(new)),
    )

    for question_id in sorted(set(old) & set(new)):
        question_diff = compare_questions(old[question_id], new[question_id])
        if question_diff.changes:
            diff.changed.append(question_diff)
        else:
            diff.identical.append(question_id)

    return diff


def render_diff(diff: ExtractionDiff, before_label: str, after_label: str) -> str:
    lines = [
        f"Comparing  {before_label}",
        f"      with  {after_label}",
        "",
        f"Identical : {len(diff.identical)}",
        f"Changed   : {len(diff.changed)}",
        f"Only in A : {len(diff.removed)}  {', '.join(diff.removed)}".rstrip(),
        f"Only in B : {len(diff.added)}  {', '.join(diff.added)}".rstrip(),
        f"Agreement : {diff.agreement:.0%}",
    ]

    if diff.is_clean:
        lines += ["", "The two runs agree on every question."]
        return "\n".join(lines) + "\n"

    for question_diff in diff.changed:
        lines += ["", "=" * 70, question_diff.source_question_id, "-" * 70]
        for change in question_diff.changes:
            if change.detail:
                lines += [f"  {change.field}:", f"    {change.detail}"]
            else:
                lines.append(f"  {change.field}: {change.before!r} -> {change.after!r}")

    return "\n".join(lines) + "\n"
