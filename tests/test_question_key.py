"""The identity a question keeps across extraction runs."""

from __future__ import annotations

import json

import pytest

from app.json_exporter import export_extraction_json
from app.question_key import paper_key, question_key, split_question_key
from app.supabase_store import question_rows
from tests.test_supabase_store import make_result


SHA = "b584940bfebbe1d89008db6378c067af0a2bf6040e299d025af301c658920cf5"


def test_key_is_twelve_hex_of_the_hash_and_the_printed_number():
    assert question_key(SHA, "17(a)") == "b584940bfebb:17(a)"
    assert paper_key(SHA) == "b584940bfebb"


def test_the_same_paper_and_number_give_the_same_key_every_run():
    assert question_key(SHA, "1") == question_key(SHA.upper(), " 1 ")


def test_a_different_paper_gives_a_different_key():
    assert question_key(SHA, "1") != question_key("a" * 64, "1")


def test_a_key_can_be_taken_apart_again():
    assert split_question_key("b584940bfebb:18(a)(ii)") == ("b584940bfebb", "18(a)(ii)")


@pytest.mark.parametrize("bad", ["", "b584940bfebb", "short:1", ":1", "b584940bfebb:"])
def test_things_that_are_not_keys_are_refused(bad):
    with pytest.raises(ValueError):
        split_question_key(bad)


def test_a_question_without_a_number_has_no_key():
    with pytest.raises(ValueError):
        question_key(SHA, "  ")


# --- where the key shows up -------------------------------------------------

def test_the_json_carries_a_key_on_every_question(tmp_path):
    path = export_extraction_json(make_result(sha=SHA), tmp_path / "out.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert [q["question_key"] for q in data["document"]["questions"]] == \
        ["b584940bfebb:1", "b584940bfebb:2(a)"]


def test_the_database_row_carries_the_same_key():
    rows = question_rows(make_result(sha=SHA), "doc", "run")
    assert rows[1]["question_key"] == "b584940bfebb:2(a)"
