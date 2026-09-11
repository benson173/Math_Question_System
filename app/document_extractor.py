from pathlib import Path

from app.document_loader import load_pdf
from app.gemini_client import GeminiClient
from app.schemas import ExtractedDocument


PROMPT_PATH = "prompts/document_extractor_v1.txt"


class DocumentExtractor:
    def __init__(self):
        self.gemini = GeminiClient()

    def extract(self, pdf_path: str | Path) -> ExtractedDocument:
        loaded = load_pdf(pdf_path)

        document = self.gemini.extract_pdf_json(
            pdf_path=loaded.file_path,
            prompt_path=PROMPT_PATH,
            schema=ExtractedDocument,
        )

        if document.file_name != loaded.file_name:
            document.file_name = loaded.file_name

        if document.page_count != loaded.page_count:
            document.page_count = loaded.page_count

        return document
