"""Ingest every PDF in inbox/pdf/, however many there are.

    python -m scripts.ingest_pdfs                  # everything, subfolders included
    python -m scripts.ingest_pdfs --verbose        # print every question, as for one PDF
    python -m scripts.ingest_pdfs --redo           # re-ingest papers already done
    python -m scripts.ingest_pdfs --keep           # leave the PDFs in the inbox
    python -m scripts.ingest_pdfs some/folder      # a different folder

A PDF lands in processed/pdf/ only if it ingested cleanly. One that raised an
error OR produced a blocking validation issue (no questions found, a question
with empty text) lands in failed/pdf/ - otherwise an empty extraction would look
like a success and the original would be filed away as done.

A paper already ingested is skipped without calling Gemini again: it is
recognised by content hash, so a renamed copy is skipped too.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import shutil
import sys
import time

from app.document_loader import calculate_sha256
from app.extraction_validator import blocking_issues
from app.paths import EXTRACTED_DIR, FAILED_PDF_DIR, INBOX_PDF_DIR, PROCESSED_PDF_DIR
from app.paper_meta import sidecar_path
from app.pipeline import PdfIngestionPipeline
from app.repository import Repository


MAX_NAME_COLLISIONS = 1000
HASH_PREFIX = 12


@dataclass
class Outcome:
    name: str
    status: str            # ok | failed | skipped | duplicate
    detail: str = ""
    questions: int = 0
    seconds: float = 0.0


# --- finding the work -------------------------------------------------------

def find_pdfs(directory: Path) -> list[Path]:
    """Every PDF under `directory`, subfolders included.

    Matched on the lower-cased suffix so a file named paper.PDF is not silently
    ignored on a case-sensitive filesystem.
    """
    return sorted(
        path for path in directory.rglob("*")
        if path.is_file() and path.suffix.lower() == ".pdf"
    )


def existing_extraction(sha256: str) -> Path | None:
    """The saved extraction for this content, if this paper was already done."""
    matches = sorted(EXTRACTED_DIR.glob(f"*-{sha256[:HASH_PREFIX]}.json"))
    return matches[0] if matches else None


# --- filing the results -----------------------------------------------------

def unique_destination(directory: Path, file_name: str) -> Path:
    """A path in `directory` that does not overwrite an existing file."""
    candidate = directory / file_name
    if not candidate.exists():
        return candidate

    stem, suffix = Path(file_name).stem, Path(file_name).suffix
    for n in range(2, MAX_NAME_COLLISIONS):
        candidate = directory / f"{stem}-{n}{suffix}"
        if not candidate.exists():
            return candidate

    raise RuntimeError(f"Too many files named {file_name} in {directory}")


def destination_directory(result) -> Path:
    """processed/ only for a clean ingestion; failed/ for a blocking issue.

    This is the rule that stops an extraction with zero questions from being
    filed away as a success.
    """
    return FAILED_PDF_DIR if blocking_issues(result.issues) else PROCESSED_PDF_DIR


def file_away(pdf_path: Path, directory: Path, inbox: Path) -> Path:
    """Move a PDF out of the inbox, keeping any folder structure it came in."""
    try:
        relative = pdf_path.relative_to(inbox)
    except ValueError:
        relative = Path(pdf_path.name)

    target_dir = directory / relative.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    destination = unique_destination(target_dir, pdf_path.name)
    shutil.move(str(pdf_path), str(destination))

    # A <stem>.meta.txt sidecar belongs to its PDF and goes where it goes.
    sidecar = sidecar_path(pdf_path)
    if sidecar.exists():
        shutil.move(str(sidecar), str(sidecar_path(destination)))
    return destination


def prune_empty_directories(root: Path) -> None:
    for path in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if path.is_dir() and not any(path.iterdir()):
            path.rmdir()


# --- reporting --------------------------------------------------------------

def format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes, seconds = divmod(int(seconds), 60)
    return f"{minutes}m{seconds:02d}s"


def write_batch_report(outcomes: list[Outcome], elapsed: float) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
    # Two batches inside one second must not overwrite each other's report.
    path = unique_destination(EXTRACTED_DIR, f"batch-{stamp}.md")

    counts: dict[str, int] = {}
    for outcome in outcomes:
        counts[outcome.status] = counts.get(outcome.status, 0) + 1

    lines = [f"# Batch {stamp}", "", "| | |", "|---|---|"]
    lines += [f"| {status} | {count} |" for status, count in sorted(counts.items())]
    lines += [
        f"| questions | {sum(o.questions for o in outcomes)} |",
        f"| elapsed | {format_duration(elapsed)} |",
        "",
        "| PDF | Status | Questions | Time | Detail |",
        "|---|---|---|---|---|",
    ]
    for outcome in outcomes:
        detail = outcome.detail.replace("|", "\\|")
        lines.append(
            f"| {outcome.name} | {outcome.status} | {outcome.questions or ''} | "
            f"{format_duration(outcome.seconds) if outcome.seconds else ''} | {detail} |"
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def print_summary(outcomes: list[Outcome], elapsed: float, report: Path) -> None:
    counts: dict[str, int] = {}
    for outcome in outcomes:
        counts[outcome.status] = counts.get(outcome.status, 0) + 1

    print("=" * 70)
    print("SUMMARY   " + "   ".join(f"{status}: {count}"
                                    for status, count in sorted(counts.items())))
    print(f"          {sum(o.questions for o in outcomes)} questions in "
          f"{format_duration(elapsed)}")
    for outcome in outcomes:
        if outcome.status != "ok":
            print(f"  {outcome.status.upper():9} {outcome.name}  {outcome.detail}")
    print(f"Report:   {report}")


# --- the run ----------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    verbose = "--verbose" in args
    redo = "--redo" in args
    keep = "--keep" in args
    positional = [a for a in args if not a.startswith("--")]
    inbox = Path(positional[0]) if positional else INBOX_PDF_DIR

    for directory in (inbox, PROCESSED_PDF_DIR, FAILED_PDF_DIR, EXTRACTED_DIR):
        directory.mkdir(parents=True, exist_ok=True)

    pdf_files = find_pdfs(inbox)
    if not pdf_files:
        print(f"No PDF files found in {inbox}.")
        return 0

    print(f"Found {len(pdf_files)} PDF(s) in {inbox}")

    # Built before anything moves, so a missing API key fails immediately
    # rather than after half the inbox has been filed away.
    repository = Repository(verbose=verbose)
    print(repository.describe_target())
    pipeline = PdfIngestionPipeline(repository=repository)

    outcomes: list[Outcome] = []
    seen: dict[str, str] = {}
    started = time.monotonic()

    try:
        for index, pdf_path in enumerate(pdf_files, start=1):
            label = str(pdf_path.relative_to(inbox))
            print("=" * 70)
            print(f"[{index}/{len(pdf_files)}] {label}")

            try:
                sha256 = calculate_sha256(pdf_path)
            except OSError as exc:
                outcomes.append(Outcome(label, "failed", f"unreadable: {exc}"))
                print(f"  unreadable: {exc}")
                continue

            if sha256 in seen:
                outcomes.append(Outcome(label, "duplicate",
                                        f"same content as {seen[sha256]}"))
                print(f"  duplicate of {seen[sha256]}, skipping")
                if not keep:
                    file_away(pdf_path, PROCESSED_PDF_DIR, inbox)
                continue
            seen[sha256] = label

            done = None if redo else existing_extraction(sha256)
            if done:
                outcomes.append(Outcome(label, "skipped", f"already ingested: {done.name}"))
                print(f"  already ingested ({done.name}), skipping - use --redo to force")
                if not keep:
                    file_away(pdf_path, PROCESSED_PDF_DIR, inbox)
                continue

            start = time.monotonic()
            try:
                result = pipeline.run_one_pdf(pdf_path)
            except Exception as exc:
                seconds = time.monotonic() - start
                detail = f"{type(exc).__name__}: {exc}"
                print(f"  failed: {detail}")
                if not keep:
                    file_away(pdf_path, FAILED_PDF_DIR, inbox)
                outcomes.append(Outcome(label, "failed", detail, seconds=seconds))
                continue

            seconds = time.monotonic() - start
            destination = destination_directory(result)
            failed = destination == FAILED_PDF_DIR
            detail = ", ".join(sorted({i.issue_code for i in blocking_issues(result.issues)}))

            if not keep:
                file_away(pdf_path, destination, inbox)

            outcomes.append(Outcome(
                name=label,
                status="failed" if failed else "ok",
                detail=detail,
                questions=len(result.document.questions),
                seconds=seconds,
            ))
            print(f"  {'failed' if failed else 'ok'}: "
                  f"{len(result.document.questions)} questions in {format_duration(seconds)}"
                  + (f" ({detail})" if detail else ""))

    except KeyboardInterrupt:
        print("\nInterrupted. Reporting what finished; the rest stayed in the inbox.")
        elapsed = time.monotonic() - started
        print_summary(outcomes, elapsed, write_batch_report(outcomes, elapsed))
        return 130

    if not keep:
        prune_empty_directories(inbox)

    elapsed = time.monotonic() - started
    print_summary(outcomes, elapsed, write_batch_report(outcomes, elapsed))

    return 1 if any(o.status == "failed" for o in outcomes) else 0


if __name__ == "__main__":
    raise SystemExit(main())
