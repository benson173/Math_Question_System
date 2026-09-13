"""What db_check reports when the database does not match."""

from __future__ import annotations

import pytest

from scripts.db_check import EXPECTED_COLUMNS, advise, probe_table, report


class FakeResponse:
    def __init__(self, data, count=None):
        self.data, self.count = data, count


class APIError(Exception):
    """Shaped like the error supabase-py raises."""

    def __init__(self, message, code=""):
        super().__init__(message)
        self.message, self.code = message, code


class FakeQuery:
    def __init__(self, client, table, columns, count=None):
        self.client, self.table_name = client, table
        self.columns, self.count = columns, count

    def limit(self, _n):
        return self

    def execute(self):
        return self.client.run(self)


class FakeClient:
    """`schema` maps a table to the columns it really has; a table left out of
    the mapping does not exist at all."""

    def __init__(self, schema, rows=None):
        self.schema, self.rows = schema, rows or {}

    def table(self, name):
        return lambda_table(self, name)

    def run(self, query):
        if query.table_name not in self.schema:
            raise APIError(f"Could not find the table 'public.{query.table_name}' "
                           f"in the schema cache", code="PGRST205")
        have = self.schema[query.table_name]
        for column in query.columns:
            if column != "*" and column not in have:
                raise APIError(f"column {query.table_name}.{column} does not exist",
                               code="42703")
        return FakeResponse([], count=self.rows.get(query.table_name, 0))


def lambda_table(client, name):
    class _Table:
        @staticmethod
        def select(*columns, count=None):
            return FakeQuery(client, name, list(columns), count)
    return _Table


FULL = {table: list(columns) for table, columns in EXPECTED_COLUMNS.items()}


# --- probing ----------------------------------------------------------------

def test_a_matching_table_has_nothing_missing():
    result = probe_table(FakeClient(FULL, {"questions": 42}), "questions",
                         EXPECTED_COLUMNS["questions"])
    assert result["exists"] is True
    assert result["missing"] == []
    assert result["rows"] == 42


def test_every_missing_column_is_listed_not_just_the_first():
    # The table exists with only what the Supabase table editor gives it.
    schema = {"source_documents": ["id", "created_at"]}
    result = probe_table(FakeClient(schema), "source_documents",
                         EXPECTED_COLUMNS["source_documents"])
    assert result["exists"] is True
    assert result["missing"] == [c for c in EXPECTED_COLUMNS["source_documents"]
                                 if c not in ("id",)]
    assert result["missing"][:4] == ["sha256", "file_name", "page_count", "byte_size"]


def test_a_table_that_is_not_there_is_told_apart_from_missing_columns():
    result = probe_table(FakeClient({}), "questions", EXPECTED_COLUMNS["questions"])
    assert result["exists"] is False
    assert "Could not find the table" in result["error"]
    assert result["missing"] == EXPECTED_COLUMNS["questions"]


def test_a_count_that_fails_does_not_fail_the_check():
    class NoCount(FakeClient):
        def run(self, query):
            if query.count == "exact":
                raise APIError("counting is off")
            return super().run(query)

    result = probe_table(NoCount(FULL), "questions", EXPECTED_COLUMNS["questions"])
    assert result["exists"] is True and result["missing"] == [] and result["rows"] is None


# --- what it prints ---------------------------------------------------------

def test_a_full_schema_reports_ok(capsys):
    results = [probe_table(FakeClient(FULL), t, c) for t, c in EXPECTED_COLUMNS.items()]
    assert report(results) is True
    printed = capsys.readouterr().out
    assert "ok" in printed and "DIFFERS" not in printed


def test_missing_columns_are_named_in_the_report(capsys):
    schema = {t: ["id", "created_at"] for t in EXPECTED_COLUMNS}
    results = [probe_table(FakeClient(schema), t, c) for t, c in EXPECTED_COLUMNS.items()]
    assert report(results) is False

    printed = capsys.readouterr().out
    assert "- sha256" in printed
    assert "- level" in printed
    assert "- images" in printed


def test_the_advice_for_existing_tables_says_nothing_is_dropped(capsys):
    schema = {t: ["id"] for t in EXPECTED_COLUMNS}
    advise([probe_table(FakeClient(schema), t, c) for t, c in EXPECTED_COLUMNS.items()])
    printed = capsys.readouterr().out
    assert "docs/supabase_schema.sql" in printed
    assert "drops nothing" in printed
    assert "information_schema.columns" in printed      # how to dump their own schema


def test_the_advice_for_absent_tables_just_says_run_the_file(capsys):
    advise([probe_table(FakeClient({}), t, c) for t, c in EXPECTED_COLUMNS.items()])
    printed = capsys.readouterr().out
    assert "not there yet" in printed
    assert "information_schema.columns" not in printed


# --- the expectations themselves --------------------------------------------

def test_every_column_the_store_writes_is_checked():
    from app.supabase_store import document_row, question_rows, run_row
    from tests.test_supabase_store import make_result

    result = make_result()
    written = {
        "source_documents": set(document_row(result)),
        "extraction_runs": set(run_row(result, "d")),
        "questions": set(question_rows(result, "d", "r")[0]),
    }
    for table, columns in written.items():
        # id is checked as well, because the store reads it back after a write.
        assert columns <= set(EXPECTED_COLUMNS[table]), table
