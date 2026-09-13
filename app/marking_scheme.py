"""Attach a marking scheme to a paper that was extracted without one.

Most papers print no answers: the marking scheme is a second PDF. Answers are
what the Solver and the Critic check against, so the two have to be joined,
and joined by the printed question number - the one thing both PDFs share.

Three parts, kept separate so each can be tested alone:
  * naming     - which PDF is a marking scheme, and for which paper
  * extraction - a Gemini call with its own prompt and schema
  * attaching  - a pure merge of answers into an ExtractedDocument
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re

from app.config import load_settings
from app.document_loader import load_pdf
from app.gemini_client import GeminiClient
from app.paths import PROMPT_MARKING_SCHEME_V1
from app.schemas import (
    ExtractedDocument,
    MarkedAnswer,
    MarkingScheme,
    MarkingSchemePayload,
)


# --- naming -------------------------------------------------------------------
#
# S4-2024-mock-ms.pdf is the marking scheme for S4-2024-mock.pdf. The suffix is
# separated by "-" or "_" so "problems.pdf" is not read as a scheme for "proble".
_SCHEME_SUFFIX = re.compile(
    r"^(?P<stem>.+?)[-_ ](?:ms|marking[-_ ]?scheme|marking|answers?|ans|"
    r"solutions?|sol|key|answer[-_ ]?key)$", re.I)


def marking_scheme_stem(file_name: str) -> str | None:
    """The paper's stem if this file name is a marking scheme, else None."""
    match = _SCHEME_SUFFIX.match(Path(file_name).stem)
    return match.group("stem") if match else None


def is_marking_scheme(file_name: str) -> bool:
    return marking_scheme_stem(file_name) is not None


@dataclass
class Pairing:
    papers: list[Path]
    schemes: dict[Path, Path]            # paper -> its marking scheme
    orphans: list[Path]                  # schemes whose paper is not in the batch


def pair_marking_schemes(pdf_files: list[Path]) -> Pairing:
    """Split a batch into papers and the schemes that belong to them.

    Matched within the same folder, by stem, case-insensitively: a scheme in
    2024/ does not attach to a paper of the same name in mock/.
    """
    papers = [p for p in pdf_files if not is_marking_scheme(p.name)]
    by_key = {(p.parent, p.stem.lower()): p for p in papers}
    schemes: dict[Path, Path] = {}
    orphans: list[Path] = []
    for path in pdf_files:
        stem = marking_scheme_stem(path.name)
        if stem is None:
            continue
        paper = by_key.get((path.parent, stem.lower()))
        if paper is None:
            orphans.append(path)
        else:
            schemes[paper] = path
    return Pairing(papers, schemes, orphans)


# --- extraction ---------------------------------------------------------------

class MarkingSchemeExtractor:
    def __init__(self):
        self.settings = load_settings()
        self.gemini = GeminiClient()

    def extract(self, pdf_path: str | Path) -> tuple[MarkingSchemePayload, MarkingScheme]:
        loaded = load_pdf(pdf_path)
        payload = self.gemini.extract_pdf_json(
            pdf_path=loaded.file_path,
            prompt_path=PROMPT_MARKING_SCHEME_V1,
            schema=MarkingSchemePayload,
            pdf_bytes=loaded.data,
        )
        record = MarkingScheme(file_name=loaded.file_name, sha256=loaded.sha256,
                               page_count=loaded.page_count)
        return payload, record


# --- attaching ----------------------------------------------------------------

@dataclass
class AttachReport:
    matched: list[str] = field(default_factory=list)
    unmatched_scheme_ids: list[str] = field(default_factory=list)
    questions_without_answer: list[str] = field(default_factory=list)
    marks_filled: list[str] = field(default_factory=list)
    answer_conflicts: list[str] = field(default_factory=list)


def _normalise_id(qid: str) -> str:
    return re.sub(r"\s+", "", qid).lower()


def attach_marking_scheme(document: ExtractedDocument, payload: MarkingSchemePayload,
                          record: MarkingScheme) -> AttachReport:
    """Merge the scheme's answers into the document, part by part.

    The scheme is the authority on answers and working: a paper that prints an
    answer is rare, and where the two disagree the paper's version is kept in
    a note rather than silently replaced. Marks are only filled in where the
    paper printed none, so a group total is never split.
    """
    report = AttachReport()
    by_id = {_normalise_id(q.source_question_id): q for q in document.questions}

    for entry in payload.answers:
        question = by_id.get(_normalise_id(entry.source_question_id))
        if question is None:
            report.unmatched_scheme_ids.append(entry.source_question_id)
            continue
        _merge(question, entry, record.file_name, report)
        if question.source_question_id not in report.matched:
            report.matched.append(question.source_question_id)

    for question in document.questions:
        if not question.answer and not question.worked_solution:
            report.questions_without_answer.append(question.source_question_id)

    record.matched = list(report.matched)
    record.unmatched_scheme_ids = list(report.unmatched_scheme_ids)
    record.questions_without_answer = list(report.questions_without_answer)
    document.marking_scheme = record
    return report


def _merge(question, entry: MarkedAnswer, scheme_name: str, report: AttachReport) -> None:
    qid = question.source_question_id

    if entry.answer:
        if question.answer and question.answer.strip() != entry.answer.strip():
            question.extraction_notes.append(
                f"The paper prints the answer {question.answer!r}; the marking scheme "
                f"{scheme_name} says {entry.answer!r}. Using the marking scheme.")
            report.answer_conflicts.append(qid)
        question.answer = entry.answer

    if entry.worked_solution:
        question.worked_solution = entry.worked_solution

    if entry.marks is not None and question.marks is None and question.group_marks is None:
        question.marks = entry.marks
        report.marks_filled.append(qid)

    for note in entry.extraction_notes:
        question.extraction_notes.append(f"Marking scheme: {note}")
