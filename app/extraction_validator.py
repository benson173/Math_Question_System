"""Check a Gemini extraction for the mistakes it actually makes.

Nothing here judges mathematics. It only asks "does this look like a faithful
copy of the PDF?" - missing questions, broken symbols, impossible page numbers.
"""

from __future__ import annotations

import re

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

        broken = find_broken_powers(q.question_text)
        if broken:
            found = ", ".join(sorted(set(broken)))
            report("POSSIBLE_BROKEN_POWER", "medium",
                   f"Question {qid} may have broken power notation: {found}", qid)

    if document.questions and document.page_count >= MIN_PAGES_FOR_DENSITY_CHECK:
        expected = document.page_count * MIN_QUESTIONS_PER_PAGE
        if len(document.questions) < expected:
            report("SUSPICIOUSLY_FEW_QUESTIONS", "medium",
                   f"Only {len(document.questions)} question(s) found in "
                   f"{document.page_count} pages. The extractor may have skipped some.")

    return issues
