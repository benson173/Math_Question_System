"""Check a Gemini extraction for the mistakes it actually makes.

Nothing here judges mathematics. It only asks "does this look like a faithful
copy of the PDF?" - missing questions, broken symbols, impossible page numbers.
"""

from __future__ import annotations

import re

from app.diagram_geometry import is_usable_region
from app.extraction_repair import find_stem_contamination
from app.schemas import ExtractedDocument, Severity, ValidationIssue


# An issue at one of these severities means the PDF did not ingest successfully
# and belongs in failed/pdf/ rather than processed/pdf/.
BLOCKING_SEVERITIES: frozenset[Severity] = frozenset({"critical"})

# A worksheet with far fewer questions than pages usually means the extractor
# skipped some. Only applied to documents long enough for the ratio to mean
# anything: a 3-page paper really can hold a single long question, so the floor
# sits above that rather than crying wolf on every short worksheet.
MIN_PAGES_FOR_DENSITY_CHECK = 5
MIN_QUESTIONS_PER_PAGE = 0.5

# "225x2" is what a flattened "225x²" looks like. Find a letter glued to a
# digit - properly written powers (x², x^2, x**2) cannot match, because neither
# "²" nor "^" nor "*" is an ASCII digit.
_BROKEN_POWER = re.compile(r"[a-zA-Z]\d+")

# Two shapes that look identical to the pattern above but are legitimate, and
# so are masked out before the search. The trade-off is deliberate: masking
# "2x2" also hides a genuinely broken "4x²", and masking "Q1" also hides an
# uppercase variable "X2". Both are rarer than the false alarms they prevent.
_DIMENSION_TOKEN = re.compile(r"\b\d[xX]\d\b")   # "a 2x2 grid"
_LABEL_TOKEN = re.compile(r"\b[A-Z]\d+\b")       # "Q1", "A2", "P6"

# A GitHub-flavoured Markdown separator row: | --- | :---: | ---: |
_TABLE_SEPARATOR = re.compile(r"^\s*\|?(\s*:?-{2,}:?\s*\|)+\s*:?-{2,}:?\s*\|?\s*$|"
                              r"^\s*\|(\s*:?-{2,}:?\s*\|)+\s*$")

# Sentence enders used to spot text duplicated inside one question.
_SENTENCE_SPLIT = re.compile(r"[。？！\n]+")
MIN_REPEATED_SENTENCE = 8


def _mask(pattern: re.Pattern[str], text: str) -> str:
    """Blank out matches while keeping the string the same length."""
    return pattern.sub(lambda m: "#" * len(m.group()), text)


def find_broken_powers(text: str) -> list[str]:
    """Return the substrings that look like a superscript flattened to a digit.

    Unlike a whole-string check, this reports every site independently, so a
    correctly written power elsewhere in the same question cannot hide a broken
    one.
    """
    masked = _mask(_LABEL_TOKEN, _mask(_DIMENSION_TOKEN, text))
    return [match.group() for match in _BROKEN_POWER.finditer(masked)]


def _cell_count(line: str) -> int:
    """Cells in a Markdown table row, ignoring the outer pipes."""
    parts = line.split("|")
    if parts and not parts[0].strip():
        parts = parts[1:]
    if parts and not parts[-1].strip():
        parts = parts[:-1]
    return len(parts)


def _pipe_blocks(text: str) -> list[list[str]]:
    """Runs of consecutive lines containing a pipe."""
    blocks: list[list[str]] = []
    current: list[str] = []

    for line in text.splitlines():
        if "|" in line:
            current.append(line)
        else:
            if len(current) >= 2:
                blocks.append(current)
            current = []

    if len(current) >= 2:
        blocks.append(current)
    return blocks


def _has_separator(block: list[str]) -> bool:
    return any(_TABLE_SEPARATOR.match(line) for line in block[:2])


def _is_table_like(block: list[str]) -> bool:
    """A separator row proves it; otherwise a steady pipe count is the signal
    that separates a table from prose that happens to contain pipes."""
    if _has_separator(block):
        return True
    return len({line.count("|") for line in block}) == 1


def find_malformed_tables(text: str) -> int:
    """Table-like blocks with no Markdown separator row.

    Without it the block renders as one run-on paragraph rather than a table,
    and nothing downstream can read the columns.
    """
    return sum(1 for block in _pipe_blocks(text)
               if _is_table_like(block) and not _has_separator(block))


def find_ragged_tables(text: str) -> list[int]:
    """Markdown tables whose rows disagree on how many cells they have.

    Usually a printed table with merged cells or a two-level header, which
    Markdown cannot express: the columns silently stop lining up.
    """
    ragged = []
    for block in _pipe_blocks(text):
        if not _has_separator(block):
            continue
        counts = {_cell_count(line) for line in block}
        if len(counts) > 1:
            ragged.append(max(counts) - min(counts))
    return ragged


def find_repeated_sentences(text: str) -> list[str]:
    """Sentences appearing more than once inside a single question.

    A part's own question copied into the shared stem shows up exactly this
    way, so the duplicate is the symptom worth reporting.
    """
    seen: dict[str, int] = {}
    for raw in _SENTENCE_SPLIT.split(text):
        sentence = " ".join(raw.split())
        if len(sentence) >= MIN_REPEATED_SENTENCE and "|" not in sentence:
            seen[sentence] = seen.get(sentence, 0) + 1
    return sorted(s for s, count in seen.items() if count > 1)


def blocking_issues(issues: list[ValidationIssue]) -> list[ValidationIssue]:
    return [issue for issue in issues if issue.severity in BLOCKING_SEVERITIES]


def has_blocking_issues(issues: list[ValidationIssue]) -> bool:
    return bool(blocking_issues(issues))


def validate_extraction(document: ExtractedDocument) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    def report(code: str, severity: Severity, message: str, qid: str | None = None) -> None:
        issues.append(ValidationIssue(
            issue_code=code,
            severity=severity,
            message=message,
            source_question_id=qid,
        ))

    if document.page_count <= 0:
        report("PAGE_COUNT_INVALID", "high", "Document page_count is invalid.")

    if not document.questions:
        report("NO_QUESTIONS_FOUND", "critical", "No questions were extracted.")

    seen_ids: set[str] = set()

    for q in document.questions:
        qid = q.source_question_id

        if not qid.strip():
            report("MISSING_QUESTION_ID", "high", "A question has no source_question_id.")
        elif qid in seen_ids:
            report("DUPLICATE_QUESTION_ID", "medium", f"Duplicate question id: {qid}", qid)
        seen_ids.add(qid)

        if not q.question_text.strip():
            report("EMPTY_QUESTION_TEXT", "critical", f"Question {qid} has empty text.", qid)

        if q.page_start <= 0 or q.page_end <= 0:
            report("PAGE_NUMBER_INVALID", "high",
                   f"Question {qid} has invalid page number.", qid)
        elif q.page_end < q.page_start:
            report("PAGE_RANGE_INVALID", "high",
                   f"Question {qid} page_end is before page_start.", qid)
        elif document.page_count > 0 and q.page_end > document.page_count:
            report("PAGE_OUT_OF_RANGE", "high",
                   f"Question {qid} claims page {q.page_end}, "
                   f"but the document has {document.page_count} page(s).", qid)

        if q.marks is not None and q.marks < 0:
            report("MARKS_INVALID", "medium",
                   f"Question {qid} has negative marks ({q.marks}).", qid)

        if q.diagram_required and not is_usable_region(q.diagram_region):
            report("DIAGRAM_REGION_UNUSABLE", "medium",
                   f"Question {qid} needs a diagram but gave no usable region; "
                   "the whole page will be rendered instead.", qid)

        malformed = find_malformed_tables(q.question_text)
        if malformed:
            report("MALFORMED_TABLE", "medium",
                   f"Question {qid} has {malformed} table-like block(s) with no "
                   "Markdown separator row, so they will not render as tables.", qid)

        ragged = find_ragged_tables(q.question_text)
        if ragged:
            report("RAGGED_TABLE", "medium",
                   f"Question {qid} has {len(ragged)} table(s) whose rows disagree on "
                   f"cell count (by up to {max(ragged)}). The printed table probably "
                   "has merged cells or a two-level header; flatten it into one "
                   "header row.", qid)

        repeated = find_repeated_sentences(q.question_text)
        if repeated:
            report("REPEATED_TEXT_IN_QUESTION", "medium",
                   f"Question {qid} repeats text verbatim, which usually means one "
                   f"part's question was copied into the shared stem: "
                   f"{repeated[0][:60]!r}", qid)

        broken = find_broken_powers(q.question_text)
        if broken:
            found = ", ".join(sorted(set(broken)))
            report("POSSIBLE_BROKEN_POWER", "medium",
                   f"Question {qid} may have broken power notation: {found}", qid)

    # Sibling-level: one part's question sitting in the stem every sibling
    # shares. Each sibling then carries a question that is not its own, which no
    # single-question check can see.
    for contamination in find_stem_contamination(document.questions):
        for qid in contamination.question_ids:
            report("STEM_CONTAMINATION", "high",
                   f"The stem shared by question {contamination.parent} ends with "
                   f"{contamination.removed!r}, which is {contamination.owner}'s own "
                   "question. Every part carries a question that is not its own.", qid)

    # Only meaningful when the paper prints marks at all: a paper with none is
    # fine, a paper that marks most questions and not others is not.
    marked = [q for q in document.questions
              if q.marks is not None or q.group_marks is not None]
    if marked:
        for q in document.questions:
            if q.marks is None and q.group_marks is None:
                report("MARKS_MISSING", "low",
                       f"Question {q.source_question_id} has no marks, but "
                       f"{len(marked)} of {len(document.questions)} questions do.",
                       q.source_question_id)

    if document.questions and document.page_count >= MIN_PAGES_FOR_DENSITY_CHECK:
        expected = document.page_count * MIN_QUESTIONS_PER_PAGE
        if len(document.questions) < expected:
            report("SUSPICIOUSLY_FEW_QUESTIONS", "medium",
                   f"Only {len(document.questions)} question(s) found in "
                   f"{document.page_count} pages. The extractor may have skipped some.")

    return issues
