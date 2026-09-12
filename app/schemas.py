from pydantic import BaseModel, Field
from typing import Literal, Optional


Severity = Literal["critical", "high", "medium", "low"]


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
    answer: Optional[str] = None
    worked_solution: Optional[str] = None
    diagram_required: bool = False
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
