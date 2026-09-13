"""Reading which paper a PDF is off its name or its sidecar."""

from __future__ import annotations

import pytest

from app.paper_meta import (
    meta_from_filename,
    meta_from_sidecar,
    parse_sidecar,
    resolve_paper_meta,
    sidecar_level,
    sidecar_path,
)


@pytest.mark.parametrize("name,year,term,exam,paper", [
    ("2526_1st_S4MATH1.pdf",       "2025-26", "1st",   None,   1),
    ("F4-2024-mock-paper1.pdf",    "2024",    None,    "mock", 1),
    ("2023-24_final_exam_p2.pdf",  "2023-24", "final", "exam", None),
    ("S5 uniform test 2025.pdf",   "2025",    None,    "test", None),
    ("dse-2022-paper-2.pdf",       "2022",    None,    "dse",  2),
    ("mid-year-hw-3.pdf",          None,      "mid",   "homework", None),
    ("上學期測驗_中四.pdf",          None,      "1st",   "test", None),
    ("mock-paper.pdf",             None,      None,    "mock", None),
])
def test_the_file_name_gives_what_it_encodes(name, year, term, exam, paper):
    meta = meta_from_filename(name)
    assert (meta.year, meta.term, meta.exam_type, meta.paper_number) == (year, term, exam, paper)
    assert meta.source == "filename"


def test_a_compact_year_must_be_two_consecutive_years():
    assert meta_from_filename("2526.pdf").year == "2025-26"
    assert meta_from_filename("2530.pdf").year is None       # not a school year
    assert meta_from_filename("1234.pdf").year is None


def test_a_bare_p1_is_not_read_as_a_paper_number():
    assert meta_from_filename("dse-P1.pdf").paper_number is None


# --- sidecar ----------------------------------------------------------------

SIDECAR = """
# who set this paper
year: 2025-26
term: 1st
exam: test            # alias for exam_type
paper: Paper 1
school: ABC College
topics: factorisation, quadratic equations、percentages
form: F4
"""


def test_every_sidecar_line_is_read():
    values = parse_sidecar(SIDECAR)
    assert values == {
        "year": "2025-26", "term": "1st", "exam_type": "test", "paper_number": 1,
        "school": "ABC College",
        "topics": ["factorisation", "quadratic equations", "percentages"],
        "level": "F4",
    }


def test_unknown_keys_and_blank_lines_are_ignored():
    assert parse_sidecar("colour: blue\n\n:\nyear:") == {}


def test_the_sidecar_sits_next_to_the_pdf():
    assert sidecar_path("inbox/pdf/S4-mock.pdf").name == "S4-mock.meta.txt"


def test_sidecar_fields_win_and_the_file_name_fills_the_rest(tmp_path):
    pdf = tmp_path / "2526_1st_S4MATH1.pdf"
    pdf.write_bytes(b"%PDF")
    sidecar_path(pdf).write_text("school: ABC College\nexam: exam\n", encoding="utf-8")

    meta = resolve_paper_meta(pdf)
    assert meta.school == "ABC College"
    assert meta.exam_type == "exam"          # sidecar
    assert meta.year == "2025-26"            # file name filled it in
    assert meta.paper_number == 1
    assert meta.source == "sidecar"


def test_no_sidecar_means_the_file_name_alone(tmp_path):
    pdf = tmp_path / "F5-mock.pdf"
    pdf.write_bytes(b"%PDF")
    assert meta_from_sidecar(pdf) is None
    assert resolve_paper_meta(pdf).source == "filename"


def test_a_level_in_the_sidecar_is_read_separately(tmp_path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF")
    sidecar_path(pdf).write_text("form: F6\n", encoding="utf-8")
    assert sidecar_level(pdf) == "F6"
    assert sidecar_level(tmp_path / "other.pdf") is None
