"""Run the three ingestion steps in order.

Pipeline is the class monitor: it tells the others when to work and reports what
happened. It does not split questions, call Gemini, write storage, or judge
mathematics itself.
"""

from __future__ import annotations

from pathlib import Path

from app.config import load_settings
from app.diagram_renderer import render_question_images
from app.document_extractor import DocumentExtractor
from app.extraction_repair import repair_control_characters, repair_shared_stems
from app.extraction_validator import blocking_issues, validate_extraction
from app.json_exporter import (diagram_output_dir, export_extraction_json,
                               extraction_output_path, history_output_path)
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

        if getattr(self.settings, "repair_extraction", True):
            stem_repairs = repair_shared_stems(result.document)
            control_repairs = repair_control_characters(result.document)

            for repair in stem_repairs:
                print(f"Repaired {repair.parent}: removed {repair.removed!r} from the "
                      f"shared stem ({repair.owner}'s own question)")
            for repair in control_repairs:
                print(f"Repaired {repair.source_question_id}: restored {repair.count} "
                      f"missing backslash(es) before {repair.character!r}")

            result.repairs = [
                f"{r.parent}: removed {r.removed!r} from the shared stem "
                f"({r.owner}'s own question)" for r in stem_repairs
            ] + [
                f"{r.source_question_id}: restored {r.count} backslash(es) as "
                f"{r.restored!r}" for r in control_repairs
            ]

        print("Step 2: Validate extraction")
        result.issues = validate_extraction(result.document)

        kinds = tuple(
            kind for kind, wanted in (
                ("diagram", self.settings.render_diagrams),
                ("table", getattr(self.settings, "render_tables", True)),
            ) if wanted
        )
        if kinds:
            print("Step 3: Render images")
            images = self._render_images(pdf_path, result, kinds)
            result.diagrams = [i for i in images if i.kind == "diagram"]
            result.tables = [i for i in images if i.kind == "table"]

        print("Step 4: Save result")
        self.repository.save_extraction_result(result)

        output_path = extraction_output_path(result)
        export_extraction_json(result, output_path)
        print("Exported:", output_path)

        export_extraction_json(result, history_output_path(result))

        report_path = markdown_output_path(output_path)
        export_extraction_markdown(result, report_path)
        print("Report:  ", report_path)

        for asset in result.diagrams + result.tables:
            how = "cropped" if asset.cropped else "full page"
            print(f"{asset.kind.title()} {asset.source_question_id}: "
                  f"{asset.image_path} ({how})")

        blocking = blocking_issues(result.issues)
        if blocking:
            codes = ", ".join(sorted({issue.issue_code for issue in blocking}))
            print(f"Done - FAILED ({codes})")
        else:
            print(f"Done - OK ({len(result.document.questions)} questions)")

        return result

    def _render_images(self, pdf_path, result, kinds):
        """Render images, but never lose an extraction over a failed one."""
        try:
            return render_question_images(
                pdf_path=pdf_path,
                document=result.document,
                output_dir=diagram_output_dir(result),
                dpi=self.settings.diagram_dpi,
                kinds=kinds,
            )
        except Exception as exc:
            print(f"Warning: could not render images ({type(exc).__name__}: {exc})")
            return []
