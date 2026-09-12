"""Run the three ingestion steps in order.

Pipeline is the class monitor: it tells the others when to work and reports what
happened. It does not split questions, call Gemini, write storage, or judge
mathematics itself.
"""

from pathlib import Path

from app.document_extractor import DocumentExtractor
from app.extraction_validator import blocking_issues, validate_extraction
from app.json_exporter import export_extraction_json, extraction_output_path
from app.repository import Repository
from app.schemas import ExtractionResult


class PdfIngestionPipeline:
    def __init__(self, extractor=None, repository=None):
        # Injectable so the orchestration can be tested without an API key.
        self.extractor = extractor or DocumentExtractor()
        self.repository = repository or Repository()

    def run_one_pdf(self, pdf_path: str | Path) -> ExtractionResult:
        """Ingest one PDF and return the result, issues included.

        Returning the result rather than None is what lets the caller tell a
        successful ingestion from one that produced no usable questions.
        """
        print("Step 1: Extract PDF")
        result = self.extractor.extract(pdf_path)

        print("Step 2: Validate extraction")
        result.issues = validate_extraction(result.document)

        print("Step 3: Save result")
        self.repository.save_extraction_result(result)

        output_path = extraction_output_path(result)
        export_extraction_json(result, output_path)
        print("Exported:", output_path)

        blocking = blocking_issues(result.issues)
        if blocking:
            codes = ", ".join(sorted({issue.issue_code for issue in blocking}))
            print(f"Done - FAILED ({codes})")
        else:
            print(f"Done - OK ({len(result.document.questions)} questions)")

        return result
