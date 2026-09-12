"""Check the Supabase connection and schema before writing anything.

    python -m scripts.db_check

Reads SUPABASE_URL and SUPABASE_SECRET_KEY from .env, connects, and confirms
each of the three tables exists with the columns the store writes. Reports row
counts so you can see whether earlier runs landed.
"""

from __future__ import annotations

import sys

from app.config import load_settings
from app.supabase_store import (
    TABLE_DOCUMENTS,
    TABLE_QUESTIONS,
    TABLE_RUNS,
    StoreError,
    connect,
)


EXPECTED_COLUMNS = {
    TABLE_DOCUMENTS: ["sha256", "file_name", "page_count", "byte_size"],
    TABLE_RUNS: ["run_id", "source_document_id", "extracted_at", "extraction_version",
                 "question_object_version", "model", "question_count", "issue_count",
                 "blocking", "issues", "repairs", "is_current"],
    TABLE_QUESTIONS: ["extraction_run_id", "source_document_id", "source_question_id",
                      "position", "question_type", "question_text", "options", "marks",
                      "group_marks", "group_marks_scope", "answer", "worked_solution",
                      "page_start", "page_end", "diagram_required", "diagram_region",
                      "table_regions", "extraction_notes", "images"],
}


def main() -> int:
    settings = load_settings()
    url, key = settings.supabase_url, settings.supabase_secret_key
    if not url or not key or url.startswith("put_") or key.startswith("put_"):
        print("SUPABASE_URL / SUPABASE_SECRET_KEY are not set in .env.")
        return 2

    try:
        client = connect(url, key)
    except StoreError as exc:
        print(exc)
        return 2

    ok = True
    for table, columns in EXPECTED_COLUMNS.items():
        try:
            response = client.table(table).select(",".join(columns)).limit(1).execute()
            count = (client.table(table).select("id", count="exact").limit(1).execute())
            total = getattr(count, "count", None)
            print(f"  ok   {table:20} {total if total is not None else '?':>6} rows")
        except Exception as exc:
            ok = False
            print(f"  FAIL {table:20} {type(exc).__name__}: {exc}")
            print(f"       expected columns: {', '.join(columns)}")

    if not ok:
        print("\nOne or more tables are missing or differ. Run docs/supabase_schema.sql "
              "in the Supabase SQL editor, or adjust app/supabase_store.py to your columns.")
        return 1

    print("\nSchema matches. The pipeline will write here on the next ingestion.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
