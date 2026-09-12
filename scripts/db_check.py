"""Check the Supabase connection and schema before writing anything.

    python3 -m scripts.db_check

Reads SUPABASE_URL and SUPABASE_SECRET_KEY from .env, connects, and checks
every column the store writes - one column at a time, so the report names the
missing ones instead of only the first. Row counts show whether earlier runs
landed.

Exit codes: 0 everything matches, 1 the schema differs, 2 not configured.
"""

from __future__ import annotations

import sys
from typing import Any

from app.config import load_settings
from app.supabase_store import (
    TABLE_DOCUMENTS,
    TABLE_QUESTIONS,
    TABLE_RUNS,
    StoreError,
    connect,
)


EXPECTED_COLUMNS = {
    TABLE_DOCUMENTS: ["id", "sha256", "file_name", "page_count", "byte_size", "level"],
    TABLE_RUNS: ["id", "run_id", "source_document_id", "extracted_at", "extraction_version",
                 "question_object_version", "model", "question_count", "issue_count",
                 "blocking", "issues", "repairs", "is_current"],
    TABLE_QUESTIONS: ["id", "extraction_run_id", "source_document_id", "source_question_id",
                      "level", "position", "question_type", "question_text", "options",
                      "marks", "group_marks", "group_marks_scope", "answer",
                      "worked_solution", "page_start", "page_end", "diagram_required",
                      "diagram_region", "table_regions", "extraction_notes", "images"],
}

SCHEMA_FILE = "docs/supabase_schema.sql"


def _describe(exc: Exception) -> str:
    message = getattr(exc, "message", None) or str(exc)
    return " ".join(str(message).split())


def probe_table(client: Any, table: str, columns: list[str]) -> dict[str, Any]:
    """One request to see if the table is readable, then one per column."""
    try:
        client.table(table).select("*").limit(1).execute()
    except Exception as exc:
        return {"table": table, "exists": False, "error": _describe(exc),
                "missing": list(columns), "rows": None}

    missing = []
    for column in columns:
        try:
            client.table(table).select(column).limit(1).execute()
        except Exception:
            missing.append(column)

    rows = None
    try:
        response = client.table(table).select("*", count="exact").limit(1).execute()
        rows = getattr(response, "count", None)
    except Exception:
        pass

    return {"table": table, "exists": True, "error": None, "missing": missing, "rows": rows}


def report(results: list[dict[str, Any]]) -> bool:
    ok = True
    for result in results:
        table = result["table"]
        if not result["exists"]:
            ok = False
            print(f"  MISSING  {table:20} {result['error']}")
            continue
        rows = result["rows"]
        count = f"{rows} rows" if rows is not None else "? rows"
        if result["missing"]:
            ok = False
            print(f"  DIFFERS  {table:20} {count}, "
                  f"{len(result['missing'])} column(s) not there:")
            for column in result["missing"]:
                print(f"           - {column}")
        else:
            print(f"  ok       {table:20} {count}, all "
                  f"{len(EXPECTED_COLUMNS[table])} columns present")
    return ok


def advise(results: list[dict[str, Any]]) -> None:
    if any(not r["exists"] for r in results):
        print(f"\nThe tables are not there yet. Open the Supabase SQL editor and run "
              f"{SCHEMA_FILE}.")
        return

    print(f"\nThe tables exist but not every column does. Open the Supabase SQL editor "
          f"and run {SCHEMA_FILE}:\nit adds exactly the columns listed above and drops "
          f"nothing, so any rows you already have are kept.")
    print("\nIf those tables are a different design you want to keep, this query prints "
          "what they\nactually have, and the row builders in app/supabase_store.py can "
          "be pointed at your names:\n")
    print("  select table_name, column_name, data_type\n"
          "    from information_schema.columns\n"
          "   where table_schema = 'public'\n"
          f"     and table_name in ('{TABLE_DOCUMENTS}', '{TABLE_RUNS}', "
          f"'{TABLE_QUESTIONS}')\n"
          "   order by table_name, ordinal_position;")


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

    print(f"Checking {url}\n")
    results = [probe_table(client, table, columns)
               for table, columns in EXPECTED_COLUMNS.items()]

    if report(results):
        print("\nSchema matches. The pipeline will write here on the next ingestion.")
        return 0

    advise(results)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
