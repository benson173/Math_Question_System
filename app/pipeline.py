"""Run the ingestion steps in order.

Pipeline is the class monitor: it tells the others when to work and reports what
happened. It does not split questions, call Gemini, write storage, or judge
mathematics itself.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import uuid

from app.config import load_settings
from app.diagram_renderer import render_question_images
from app.document_extractor import DocumentExtractor
from app.extraction_repair import (repair_control_characters,
                                   repair_dependencies,
                                   repair_shared_stems,
                                   repair_undelimited_latex)
from app.extraction_validator import blocking_issues, validate_extraction
from app.json_exporter import (diagram_output_dir, export_extraction_json,
                               extraction_output_path, history_output_path)
from app.markdown_exporter import export_extraction_markdown, markdown_output_path
from app.marking_scheme import AttachReport, attach_marking_scheme
from app.repository import Repository
from app.schemas import ExtractionResult, ExtractionRun


class PdfIngestionPipeline:
    def __init__(self, extractor=None, repository=None, settings=None,
                 marking_scheme_extractor=None):
        # Injectable so the orchestration can be tested without an API key.
        self.extractor = extractor or DocumentExtractor()
        self.repository = repository or Repository()
        self.settings = settings or load_settings()
        # Built only when a marking scheme actually turns up: most batches
        # have none, and constructing it needs the Gemini key.
        self._marking_scheme_extractor = marking_scheme_extractor

    @property
    def marking_scheme_extractor(self):
        if self._marking_scheme_extractor is None:
            from app.marking_scheme import MarkingSchemeExtractor
            self._marking_scheme_extractor = MarkingSchemeExtractor()
        return self._marking_scheme_extractor

    # --- the whole thing ------------------------------------------------------

    def run_one_pdf(self, pdf_path: str | Path,
                    marking_scheme_path: str | Path | None = None) -> ExtractionResult:
        """Ingest one PDF and return the result, issues included.

        Returning the result rather than None is what lets the caller tell a
        successful ingestion from one that produced no usable questions.
        """
        print("Step 1: Extract PDF")
        result = self.extractor.extract(pdf_path)

        if getattr(self.settings, "repair_extraction", True):
            self._repair(result)

        if marking_scheme_path is not None:
            print("Step 1b: Attach marking scheme")
            self._attach(result, marking_scheme_path)

        return self.finish(result, pdf_path)

    def attach_marking_scheme(self, result: ExtractionResult,
                              marking_scheme_path: str | Path) -> ExtractionResult:
        """Add a marking scheme to a paper extracted earlier, as a new run.

        The questions are unchanged, so the JSON and the database row for the
        paper are the same; the run is new because the answers are. Images
        are not re-rendered: the paper's PDF may no longer be in the inbox
        and the earlier run's images still stand.
        """
        print("Step 1b: Attach marking scheme")
        self._attach(result, marking_scheme_path)
        result.run = self._new_run(result)
        return self.finish(result, pdf_path=None)

    def finish(self, result: ExtractionResult, pdf_path: str | Path | None) -> ExtractionResult:
        """Validate, render, save, export - everything after extraction."""
        print("Step 2: Validate extraction")
        result.issues = validate_extraction(result.document)

        kinds = tuple(
            kind for kind, wanted in (
                ("diagram", self.settings.render_diagrams),
                ("table", getattr(self.settings, "render_tables", True)),
            ) if wanted
        )
        if kinds and pdf_path is not None:
            print("Step 3: Render images")
            images = self._render_images(pdf_path, result, kinds)
            result.diagrams = [i for i in images if i.kind == "diagram"]
            result.tables = [i for i in images if i.kind == "table"]

        # The JSON is written before anything that can fail remotely. It is the
        # archive: an extraction that reached this point cost an API call, and a
        # database that is down must not turn it into a paper filed as failed.
        print("Step 4: Save result")
        output_path = extraction_output_path(result)
        export_extraction_json(result, output_path)
        print("Exported:", output_path)

        export_extraction_json(result, history_output_path(result))

        report_path = markdown_output_path(output_path)
        export_extraction_markdown(result, report_path)
        print("Report:  ", report_path)

        try:
            self.repository.save_extraction_result(result)
        except Exception as exc:
            result.database_error = f"{type(exc).__name__}: {exc}"
            print(f"Warning: not saved to the database ({result.database_error}).\n"
                  f"         The JSON is on disk; push it later with: "
                  f"python3 -m scripts.db_push")

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

    # --- the steps ------------------------------------------------------------

    def _repair(self, result: ExtractionResult) -> None:
        stem_repairs = repair_shared_stems(result.document)
        control_repairs = repair_control_characters(result.document)
        latex_repairs = repair_undelimited_latex(result.document)
        dependency_repairs = repair_dependencies(result.document)

        for repair in stem_repairs:
            print(f"Repaired {repair.parent}: removed {repair.removed!r} from the "
                  f"shared stem ({repair.owner}'s own question)")
        for repair in control_repairs:
            print(f"Repaired {repair.source_question_id}: restored {repair.count} "
                  f"missing backslash(es) before {repair.character!r}")
        for repair in latex_repairs:
            print(f"Repaired {repair.source_question_id}: delimited formula "
                  f"{repair.line[:48]!r}")
        for repair in dependency_repairs:
            print(f"Repaired {repair.source_question_id}: depends on "
                  f"{', '.join(repair.depends_on)} ({repair.reason})")

        result.repairs = [
            f"{r.parent}: removed {r.removed!r} from the shared stem "
            f"({r.owner}'s own question)" for r in stem_repairs
        ] + [
            f"{r.source_question_id}: restored {r.count} backslash(es) as "
            f"{r.restored!r}" for r in control_repairs
        ] + [
            f"{r.source_question_id}: delimited formula {r.line[:48]!r}"
            for r in latex_repairs
        ] + [
            f"{r.source_question_id}: depends_on {r.depends_on} ({r.reason})"
            for r in dependency_repairs
        ]

    def _attach(self, result: ExtractionResult, marking_scheme_path: str | Path) -> AttachReport:
        payload, record = self.marking_scheme_extractor.extract(marking_scheme_path)
        report = attach_marking_scheme(result.document, payload, record)
        print(f"Marking scheme {record.file_name}: {len(report.matched)} of "
              f"{len(result.document.questions)} questions matched"
              + (f", {len(report.unmatched_scheme_ids)} scheme entries unmatched"
                 if report.unmatched_scheme_ids else "")
              + (f", marks filled for {len(report.marks_filled)}"
                 if report.marks_filled else ""))
        result.repairs.append(
            f"answers attached from {record.file_name}: {len(report.matched)} matched"
            + (f", unmatched {report.unmatched_scheme_ids}" if report.unmatched_scheme_ids else ""))
        return report

    def _new_run(self, result: ExtractionResult) -> ExtractionRun:
        previous = result.run
        return ExtractionRun(
            run_id=uuid.uuid4().hex[:12],
            extracted_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            extraction_version=previous.extraction_version if previous
            else self.settings.extraction_version,
            question_object_version=previous.question_object_version if previous
            else self.settings.question_object_version,
            model=previous.model if previous else self.settings.gemini_extractor_model,
            prompt_sha256=previous.prompt_sha256 if previous else None,
        )

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
