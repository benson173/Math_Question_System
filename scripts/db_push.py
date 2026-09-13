"""Push extractions already on disk into Supabase, without calling Gemini.

    python3 -m scripts.db_push                 # every JSON in data/extracted
    python3 -m scripts.db_push a.json b.json   # just these
    python3 -m scripts.db_push --force         # re-push runs already in the database

Every ingestion writes data/extracted/<paper>-<hash>.json. That file holds the
whole result, so the database can be filled from it - after setting up Supabase
for the first time, or after a schema fix - without spending another API call
on papers that are already extracted.

A run whose run_id is already in extraction_runs is skipped, so this is safe to
run repeatedly.

Exit codes: 0 nothing went wrong, 1 at least one file failed, 2 not configured.
"""

from __future__ import annotations

import sys
from pathlib import Path

from app.config import load_settings
from app.extraction_io import load_extractions
from app.level import resolve_level
from app.paper_meta import meta_from_filename
from app.paths import EXTRACTED_DIR
from app.schemas import ExtractionResult
from app.supabase_store import TABLE_RUNS, StoreError, SupabaseStore, connect


def load_results(paths: list[Path]) -> list[tuple[Path, ExtractionResult]]:
    """Read each file, keeping the path so a failure can be named."""
    return load_extractions(paths, on_skip=lambda path, exc: print(
        f"  skipped  {path.name}  not an extraction ({type(exc).__name__})"))


def fill_in_level(result: ExtractionResult) -> str | None:
    """Work out the form for a JSON written before levels existed.

    Re-reading the file name costs nothing and is the same rule the pipeline
    uses, so an old extraction still lands with its form rather than a null.
    """
    if result.document.level:
        return None
    resolved = resolve_level(result.document.file_name, result.document.level_text)
    if not resolved.level:
        return None
    result.document.level = resolved.level
    result.document.level_source = resolved.source
    return resolved.level


def fill_in_paper(result: ExtractionResult) -> bool:
    """Read the paper's year/term/type off the file name for a JSON without it."""
    if result.document.paper is not None:
        return False
    meta = meta_from_filename(result.document.file_name)
    if not any(v for k, v in meta.model_dump().items() if k != "source"):
        return False
    result.document.paper = meta
    return True


def already_pushed(client, run_id: str) -> bool:
    response = client.table(TABLE_RUNS).select("run_id").eq("run_id", run_id).limit(1).execute()
    return bool(getattr(response, "data", None))


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    force = "--force" in args
    positional = [a for a in args if not a.startswith("--")]

    settings = load_settings()
    url, key = settings.supabase_url, settings.supabase_secret_key
    if not url or not key or url.startswith("put_") or key.startswith("put_"):
        print("SUPABASE_URL / SUPABASE_SECRET_KEY are not set in .env, so there is "
              "nowhere to push to.")
        return 2

    paths = [Path(a) for a in positional] or sorted(EXTRACTED_DIR.glob("*.json"))
    if not paths:
        print(f"No extraction JSON found in {EXTRACTED_DIR}. Ingest a PDF first.")
        return 0

    try:
        store = SupabaseStore(connect(url, key))
    except StoreError as exc:
        print(exc)
        return 2

    print(f"Pushing to {url}\n")
    pushed = skipped = failed = questions = 0

    for path, result in load_results(paths):
        name = result.document.file_name
        run_id = result.run.run_id if result.run else None

        if run_id is None:
            print(f"  skipped  {name}  no run id in {path.name}")
            skipped += 1
            continue

        added_level = fill_in_level(result)
        if added_level:
            print(f"  level    {name}  read {added_level} off the file name")
        if fill_in_paper(result):
            print(f"  paper    {name}  read year/term/type off the file name")

        try:
            if already_pushed(store.client, run_id):
                if not force:
                    print(f"  already  {name}  run {run_id[:8]} is in the database")
                    skipped += 1
                    continue
                store.delete_run(run_id)           # --force: replace, never duplicate

            outcome = store.save(result)
        except Exception as exc:
            failed += 1
            print(f"  FAILED   {name}  {type(exc).__name__}: "
                  f"{' '.join(str(getattr(exc, 'message', exc)).split())}")
            continue

        pushed += 1
        questions += outcome.questions
        superseded = (f", superseded {outcome.superseded_runs} earlier run(s)"
                      if outcome.superseded_runs else "")
        print(f"  pushed   {name}  {outcome.questions} questions as run "
              f"{outcome.run_id[:8]}{superseded}")

    print(f"\n{pushed} pushed ({questions} questions), {skipped} skipped, {failed} failed")
    if failed:
        print("A failure usually means the schema does not match. Run "
              "python3 -m scripts.db_check.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
