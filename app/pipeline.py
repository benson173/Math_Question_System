"""Run the three ingestion steps in order.

Pipeline is the class monitor: it tells the others when to work and reports what
happened. It does not split questions, call Gemini, write storage, or judge
mathematics itself.
"""

from __future__ import annotations

from pathlib import Path

from app.config import load_settings
from app.diagram_renderer import render_diagrams
from app.document_extractor import DocumentExtractor
from app.extraction_validator import blocking_issues, validate_extraction
from app.json_exporter import diagram_output_dir, export_extraction_json, extraction_output_path
from app.markdown_exporter import export_extraction_markdown, markdown_output_path
from app.repository import Repository
from app.schemas import ExtractionResult


class PdfIngestionPipeline:
    def __init__(self, extractor=None, repository=None, settings=None):
        # Injectable so the orchestration can be tested without an API key.
        self.extractor = extractor or DocumentExtractor()
        self.repository = repository or Repository()
        self.settings = settings or load_settings()

    def run_one_pdf(self, pdf_path: str | Path) -> ExtractionResult:
        """Ingest one PDF and return the result, issues included.

        Returning the result rather than None is what lets the caller tell a
        successful ingestion from one that produced no usable questions.
        """
        print("Step 1: Extract PDF")
        result = self.extractor.extract(pdf_path)

        print("Step 2: Validate extraction")
        result.issues = validate_extraction(result.document)

        if self.settings.render_diagrams:
            print("Step 3: Render diagrams")
            result.diagrams = self._render_diagrams(pdf_path, result)

        print("Step 4: Save result")
        self.repository.save_extraction_result(result)

        output_path = extraction_output_path(result)
        export_extraction_json(result, output_path)
        print("Exported:", output_path)

        report_path = markdown_output_path(output_path)
        export_extraction_markdown(result, report_path)
        print("Report:  ", report_path)

        for asset in result.diagrams:
            kind = "cropped" if asset.cropped else "full page"
            print(f"Diagram {asset.source_question_id}: {asset.image_path} ({kind})")

        blocking = blocking_issues(result.issues)
        if blocking:
            codes = ", ".join(sorted({issue.issue_code for issue in blocking}))
            print(f"Done - FAILED ({codes})")
        else:
            print(f"Done - OK ({len(result.document.questions)} questions)")

        return result

    def _render_diagrams(self, pdf_path, result):
        """Render diagrams, but never lose an extraction over a failed image."""
        try:
            return render_diagrams(
                pdf_path=pdf_path,
                document=result.document,
                output_dir=diagram_output_dir(result),
                dpi=self.settings.diagram_dpi,
            )
        except Exception as exc:
            print(f"Warning: could not render diagrams ({type(exc).__name__}: {exc})")
            return []
