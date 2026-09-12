"""Turn a PDF into questions, and record where they came from.

The extractor is the copying clerk. It asks Gemini for the questions only -
file name, page count and hash are facts the loader already established, so the
model is never given a chance to guess them wrong.
"""

from datetime import datetime, timezone
from pathlib import Path
import uuid

from app.config import load_settings
from app.document_loader import LoadedDocument, load_pdf
from app.gemini_client import GeminiClient
from app.paths import PROMPT_DOCUMENT_EXTRACTOR_V1
from app.schemas import (
    ExtractedDocument,
    ExtractionResult,
    ExtractionRun,
    QuestionExtractionPayload,
    SourceDocument,
)


class DocumentExtractor:
    def __init__(self):
        self.settings = load_settings()
        self.gemini = GeminiClient()

    def extract(self, pdf_path: str | Path) -> ExtractionResult:
        """Return the questions plus the provenance needed to store them.

        `issues` is left empty: validating the result is the validator's job.
        """
        loaded = load_pdf(pdf_path)

        payload = self.gemini.extract_pdf_json(
            pdf_path=loaded.file_path,
            prompt_path=PROMPT_DOCUMENT_EXTRACTOR_V1,
            schema=QuestionExtractionPayload,
            pdf_bytes=loaded.data,
        )

        document = ExtractedDocument(
            file_name=loaded.file_name,
            page_count=loaded.page_count,
            questions=list(payload.questions),
        )

        return ExtractionResult(
            document=document,
            issues=[],
            source=self._describe_source(loaded),
            run=self._describe_run(),
        )

    @staticmethod
    def _describe_source(loaded: LoadedDocument) -> SourceDocument:
        return SourceDocument(
            file_name=loaded.file_name,
            sha256=loaded.sha256,
            page_count=loaded.page_count,
            byte_size=loaded.byte_size,
        )

    def _describe_run(self) -> ExtractionRun:
        return ExtractionRun(
            run_id=uuid.uuid4().hex[:12],
            extracted_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            extraction_version=self.settings.extraction_version,
            question_object_version=self.settings.question_object_version,
            model=self.settings.gemini_extractor_model,
        )
