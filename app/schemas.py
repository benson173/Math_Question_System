from pydantic import BaseModel, Field
from typing import Optional


class ExtractedQuestion(BaseModel):
    source_question_id: str
    page_start: int
    page_end: int
    question_text: str
    marks: Optional[float] = None
    answer: Optional[str] = None
    worked_solution: Optional[str] = None
    diagram_required: bool = False
    extraction_notes: list[str] = Field(default_factory=list)


class ExtractedDocument(BaseModel):
    file_name: str
    page_count: int
    questions: list[ExtractedQuestion]


class ValidationIssue(BaseModel):
    issue_code: str
    severity: str
    message: str


class ExtractionResult(BaseModel):
    document: ExtractedDocument
    issues: list[ValidationIssue] = Field(default_factory=list)
