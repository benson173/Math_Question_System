from pydantic import BaseModel, Field
from typing import Literal, Optional


Severity = Literal["critical", "high", "medium", "low"]

# Gemini reports boxes on a 0-1000 grid relative to the page, ordered
# [y_min, x_min, y_max, x_max]. Kept as named fields so the ordering cannot be
# mixed up on the way through.
REGION_SCALE = 1000


class DiagramRegion(BaseModel):
    """Where a diagram sits, in Gemini's 0-1000 page coordinates."""

    page: int
    y_min: int
    x_min: int
    y_max: int
    x_max: int


class ExtractedQuestion(BaseModel):
    """One question, exactly as printed in the PDF.

    Sub-questions are separate entries. `source_question_id` follows the
    parent(part) convention, e.g. "1", "1(a)", "1(a)(i)".
    """

    source_question_id: str
    page_start: int
    page_end: int
    question_text: str
    marks: Optional[float] = None
    # Papers often print one mark total for a whole question whose parts are
    # separate entries here. Recording that as data beats a free-text note:
    # group_marks=4, group_marks_scope="2" for "Question 2 ... (4 marks)".
    group_marks: Optional[float] = None
    group_marks_scope: Optional[str] = None
    answer: Optional[str] = None
    worked_solution: Optional[str] = None
    diagram_required: bool = False
    diagram_region: Optional[DiagramRegion] = None
    extraction_notes: list[str] = Field(default_factory=list)


class QuestionExtractionPayload(BaseModel):
    """What Gemini is asked to return.

    Deliberately narrower than ExtractedDocument: file_name and page_count are
    facts we already know from the PDF itself, so asking the model for them only
    invites it to guess wrong.
    """

    questions: list[ExtractedQuestion]


class ExtractedDocument(BaseModel):
    file_name: str
    page_count: int
    questions: list[ExtractedQuestion]


class SourceDocument(BaseModel):
    """Identity of the PDF the questions came from."""

    file_name: str
    sha256: str
    page_count: int
    byte_size: int


class ExtractionRun(BaseModel):
    """Which code and model produced this extraction."""

    run_id: str
    extracted_at: str
    extraction_version: str
    question_object_version: str
    model: str


class DiagramAsset(BaseModel):
    """An image this system rendered from the PDF.

    Kept out of ExtractedQuestion on purpose: the Question Object stays the
    standard table every later stage reads, and what we produced alongside it
    lives here.
    """

    source_question_id: str
    page: int
    image_path: str
    cropped: bool
    width: int
    height: int


class ValidationIssue(BaseModel):
    issue_code: str
    severity: Severity
    message: str
    source_question_id: Optional[str] = None


class ExtractionResult(BaseModel):
    document: ExtractedDocument
    issues: list[ValidationIssue] = Field(default_factory=list)
    source: Optional[SourceDocument] = None
    run: Optional[ExtractionRun] = None
    diagrams: list[DiagramAsset] = Field(default_factory=list)
    repairs: list[str] = Field(default_factory=list)
