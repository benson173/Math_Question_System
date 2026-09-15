"""Compulsory Part, M1 or M2 - read off the file name, and kept apart after that."""

from __future__ import annotations

import pytest

from app.analyzer import build_prompt, errors_block, skills_block
from app.extraction_validator import validate_extraction
from app.module import MODULES, find_modules, parse_module, resolve_module
from app.paper_meta import sidecar_path, sidecar_module
from app.rpdice import validate_analysis
from app.schemas import ExtractedDocument, ExtractedQuestion
from app.taxonomy import load_taxonomy
from tests.test_rpdice import analysis
from tests.test_supabase_store import make_result


TAX = load_taxonomy()


# --- reading it off a name --------------------------------------------------

@pytest.mark.parametrize("name,expected", [
    ("dse-m1-2024.pdf", "M1"),
    ("S6-M2-mock.pdf", "M2"),
    ("2024-DSE-Module 1.pdf", "M1"),
    ("module2_paper.pdf", "M2"),
    ("MATHM1-2025.pdf", "M1"),             # the compact spelling
    ("2526_S6MATHM2.pdf", "M2"),
    ("S6M1-mock.pdf", "M1"),               # form then module
    ("數學延伸部分單元二.pdf", "M2"),
    ("Calculus and Statistics.pdf", "M1"),
    ("代數與微積分.pdf", "M2"),
])
def test_a_module_in_the_name_is_read(name, expected):
    assert parse_module(name) == expected
    assert expected in MODULES


@pytest.mark.parametrize("name", [
    "2526_1st_S4MATH1.pdf",                # Maths paper 1, not M1
    "2526_1st_S6MATH2.pdf",                # Maths paper 2, not M2
    "MATH1-S4.pdf",
    "form1-test.pdf",
    "term1-exam.pdf",
    "F5-mock-paper1.pdf",
    "2526M2.pdf",                          # a bare digit before M is too ambiguous
])
def test_a_paper_number_is_not_a_module(name):
    assert parse_module(name) is None


def test_two_modules_named_is_no_answer():
    assert find_modules("M1 and M2 comparison") == ["M1", "M2"]
    assert parse_module("M1 and M2 comparison") is None


# --- which source wins ------------------------------------------------------

def test_the_file_name_wins_over_the_paper():
    resolved = resolve_module("S6-M2-mock.pdf", "Module 1 (Calculus and Statistics)")
    assert (resolved.module, resolved.source) == ("M2", "filename")


def test_the_paper_answers_when_the_name_does_not():
    resolved = resolve_module("mock-2024.pdf", "Module 1 (Calculus and Statistics)")
    assert (resolved.module, resolved.source) == ("M1", "paper")


def test_a_sidecar_outranks_both(tmp_path):
    pdf = tmp_path / "mock.pdf"
    pdf.write_bytes(b"%PDF")
    sidecar_path(pdf).write_text("module: M2\n", encoding="utf-8")
    assert sidecar_module(pdf) == "M2"
    assert resolve_module("dse-m1.pdf", None, sidecar_module(pdf)).module == "M2"


def test_nothing_said_means_compulsory_and_says_so():
    resolved = resolve_module("2526_1st_S4MATH1.pdf", None)
    assert (resolved.module, resolved.source) == ("compulsory", "default")


# --- what the validator says ------------------------------------------------

def document(file_name="S6-M2-mock.pdf", module="M2", module_source="filename",
             module_text=None):
    return ExtractedDocument(
        file_name=file_name, page_count=1, level="F6", level_source="filename",
        module=module, module_source=module_source, module_text=module_text,
        questions=[ExtractedQuestion(source_question_id="1", page_start=1, page_end=1,
                                     question_text="求 dy/dx。")])


def codes(doc):
    return sorted(i.issue_code for i in validate_extraction(doc))


def test_agreement_is_silent():
    assert codes(document(module_text="Module 2 (Algebra and Calculus)")) == []
    assert codes(document(file_name="mock.pdf", module="compulsory",
                          module_source="default")) == []


def test_the_name_and_the_paper_disagreeing_is_reported():
    issues = validate_extraction(document(module_text="Module 1"))
    codes_found = {i.issue_code: i for i in issues}
    assert "MODULE_MISMATCH" in codes_found
    assert codes_found["MODULE_MISMATCH"].severity == "medium"
    assert "M2" in codes_found["MODULE_MISMATCH"].message


# --- the taxonomy is split by module ----------------------------------------

def test_a_compulsory_paper_never_sees_extended_part_skills():
    ids = {s.skill_id for s in TAX.skills_for_module("compulsory")}
    assert "na.factor.dos" in ids
    assert not any(i.startswith(("m1.", "m2.")) for i in ids)


def test_an_extended_paper_gets_its_own_module_and_the_compulsory_part():
    m1 = {s.skill_id for s in TAX.skills_for_module("M1")}
    assert {"m1.binom.probability", "m1.def.trapezoidal", "na.factor.dos"} <= m1
    assert not any(i.startswith("m2.") for i in m1)

    m2 = {s.skill_id for s in TAX.skills_for_module("M2")}
    assert {"m2.matrix.inverse-3", "m2.vector.cross", "na.quad.solve-formula"} <= m2
    assert not any(i.startswith("m1.") for i in m2)


def test_module_skills_carry_no_foundation_flag():
    for skill in TAX.skills.values():
        if skill.strand in ("m1", "m2"):
            assert skill.foundation is None, skill.skill_id


def test_the_module_strands_are_covered_by_error_patterns():
    for prefix in ("m1.", "m2."):
        errors = [e for e in TAX.errors.values()
                  if any(s.startswith(prefix) for s in e.skills)]
        assert len(errors) >= 10, prefix


# --- the prompt and the analysis check --------------------------------------

def test_the_prompt_carries_only_this_paper_s_syllabus():
    result = make_result()
    result.document.module = "M1"
    prompt = build_prompt(result, TAX)
    assert "Module 1 (Calculus and Statistics)" in prompt
    assert "m1.binom.probability |" in prompt
    assert "m2.matrix.multiply |" not in prompt
    assert "{MODULE}" not in prompt

    result.document.module = "compulsory"
    compulsory = build_prompt(result, TAX)
    assert "Compulsory Part" in compulsory
    assert "m1." not in compulsory.split("SKILLS")[1]


def test_the_error_list_follows_the_skill_list():
    assert "err.diff.chain-rule-missed |" in errors_block(TAX, "M1")
    assert "err.matrix.commute |" not in errors_block(TAX, "M1")
    assert "err.dos.as-square-of-difference |" in errors_block(TAX, "M1")
    assert "err.diff.chain-rule-missed |" not in errors_block(TAX, "compulsory")


def test_skills_block_labels_the_syllabus():
    assert skills_block(TAX, "M2").startswith("SKILLS for M2")


def test_an_analysis_using_the_other_module_is_an_error():
    wrong = analysis(skills=("m2.matrix.multiply",), errors=())
    issues = validate_analysis(wrong, "求 A²。", TAX, module="M1")
    assert "SKILL_WRONG_MODULE" in {i.issue_code for i in issues}

    right = analysis(skills=("m1.binom.probability",), errors=())
    assert "SKILL_WRONG_MODULE" not in {
        i.issue_code for i in validate_analysis(right, "求機率。", TAX, module="M1")}


def test_without_a_module_no_such_check_is_made():
    wrong = analysis(skills=("m2.matrix.multiply",), errors=())
    assert "SKILL_WRONG_MODULE" not in {
        i.issue_code for i in validate_analysis(wrong, "求 A²。", TAX)}


# --- it reaches the rows and the reports ------------------------------------

def test_the_module_reaches_every_row_and_report(tmp_path):
    from app.analysis_store import analysis_rows
    from app.markdown_exporter import render_markdown
    from app.supabase_store import document_row, question_rows
    from tests.test_rpdice import make_analysis_result

    result = make_result()
    result.document.module = "M1"
    result.document.module_source = "filename"
    assert document_row(result)["module"] == "M1"
    assert all(row["module"] == "M1" for row in question_rows(result, "d", "r"))
    assert "M1 (from filename)" in render_markdown(result, tmp_path / "r.md")
    assert analysis_rows(make_analysis_result(module="M1"))[0]["module"] == "M1"


def test_an_unknown_module_is_left_out_of_the_document_row():
    from app.supabase_store import document_row
    result = make_result()
    result.document.module = None
    assert "module" not in document_row(result)
