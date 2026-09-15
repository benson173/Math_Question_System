"""The skill and error vocabularies: valid as shipped, and checked when edited."""

from __future__ import annotations



import pytest

from app.taxonomy import (
    ErrorPattern,
    Skill,
    load_taxonomy,
    read_error_patterns,
    read_skills,
    validate,
)


# --- the shipped files ------------------------------------------------------

def test_the_shipped_taxonomy_is_valid():
    taxonomy = load_taxonomy()
    assert len(taxonomy.skills) > 300
    assert len(taxonomy.errors) > 60


def test_every_strand_form_and_unit_is_represented():
    taxonomy = load_taxonomy()
    assert {s.strand for s in taxonomy.skills.values()} == {"na", "ms", "dh", "fl",
                                                            "m1", "m2"}
    assert {s.form for s in taxonomy.skills.values()} == {"F1", "F2", "F3", "F4", "F5", "F6"}
    units = {s.unit for s in taxonomy.skills.values()}
    for unit in ("Quadratic equations in one unknown", "Basic properties of circles",
                 "Permutation and combination", "Measures of dispersion", "Factorisation"):
        assert unit in units


def test_the_worked_example_from_the_spec_is_in_the_taxonomy():
    # Factorise 1 − 225x²: recognise the square, then the identity.
    taxonomy = load_taxonomy()
    dos = taxonomy.skills["na.factor.dos"]
    assert "na.factor.recognise-square" in dos.prerequisites
    assert taxonomy.errors["err.dos.as-square-of-difference"].skills[0] == "na.factor.dos"


def test_prerequisites_close_over_the_chain():
    taxonomy = load_taxonomy()
    chain = taxonomy.prerequisites_closure("na.quad.symmetric-functions")
    assert chain[0] == "na.quad.sum-product"           # nearest first
    assert "na.identity.expand" in chain                # several steps down


def test_lookups_by_form_unit_and_skill():
    taxonomy = load_taxonomy()
    assert all(s.form == "F4" for s in taxonomy.skills_for_form("F4"))
    assert taxonomy.skills_in_unit("Locus")
    assert taxonomy.errors_for_skill("na.log.laws")


# --- what the validator catches ---------------------------------------------

def skill(skill_id="na.x.y", form="F4", foundation="foundation", prerequisites=(), **kw):
    defaults = dict(skill_id=skill_id, strand=skill_id.split(".")[0], unit="U",
                    name_en="n", name_zh="名", form=form, foundation=foundation,
                    prerequisites=tuple(prerequisites))
    defaults.update(kw)
    return Skill(**defaults)


def error(error_id="err.x.y", skills=("na.x.y",)):
    return ErrorPattern(error_id=error_id, name_en="n", name_zh="名", skills=tuple(skills))


def test_a_clean_pair_has_no_problems():
    assert validate([skill()], [error()]) == []


@pytest.mark.parametrize("bad,expected", [
    ([skill(), skill()], "appears more than once"),
    ([skill(skill_id="bad id", strand="na")], "not <strand>.<unit>.<slug>"),
    ([skill(skill_id="ms.x.y", strand="na")], "says strand"),
    ([skill(form="F7")], "not F1-F6"),
    ([skill(form="F4", foundation=None)], "no foundation flag"),
    ([skill(form="F2", foundation="foundation")], "KS3"),
    ([skill(prerequisites=("na.nope.nope",))], "does not exist"),
    ([skill(prerequisites=("na.x.y",))], "lists itself"),
    ([skill(name_zh="")], "missing an English or Chinese name"),
])
def test_each_skill_fault_is_named(bad, expected):
    problems = validate(bad, [])
    assert any(expected in p for p in problems), problems


def test_a_prerequisite_cycle_is_named():
    a = skill("na.a.a", prerequisites=("na.b.b",))
    b = skill("na.b.b", prerequisites=("na.a.a",))
    problems = validate([a, b], [])
    assert any("cycle" in p and "na.a.a" in p for p in problems)


@pytest.mark.parametrize("bad,expected", [
    ([error(), error()], "appears more than once"),
    ([error(error_id="oops")], "not err.<topic>.<slug>"),
    ([error(skills=())], "belongs to no skill"),
    ([error(skills=("na.gone.gone",))], "does not exist"),
])
def test_each_error_fault_is_named(bad, expected):
    problems = validate([skill()], bad)
    assert any(expected in p for p in problems), problems


def test_loading_an_invalid_file_raises_with_every_problem(tmp_path):
    skills = tmp_path / "skills.csv"
    skills.write_text("skill_id,strand,unit,name_en,name_zh,form,foundation,prerequisites\n"
                      "# a comment line\n"
                      "na.a.a,na,U,n,名,F9,F,na.zzz.zzz\n", encoding="utf-8")
    errors = tmp_path / "errors.csv"
    errors.write_text("error_id,name_en,name_zh,skills,description\n", encoding="utf-8")
    with pytest.raises(ValueError) as info:
        load_taxonomy(skills, errors)
    message = str(info.value)
    assert "not F1-F6" in message and "does not exist" in message


def test_comments_and_blank_lines_are_skipped(tmp_path):
    path = tmp_path / "s.csv"
    path.write_text("skill_id,strand,unit,name_en,name_zh,form,foundation,prerequisites\n\n"
                    "# ---- section ----\n"
                    "na.a.a,na,U,n,名,F1,,\n", encoding="utf-8")
    assert [s.skill_id for s in read_skills(path)] == ["na.a.a"]
    assert read_skills(path)[0].foundation is None


def test_error_rows_read_their_skill_lists(tmp_path):
    path = tmp_path / "e.csv"
    path.write_text("error_id,name_en,name_zh,skills,description\n"
                    "err.a.b,n,名,na.a.a; na.b.b,why\n", encoding="utf-8")
    assert read_error_patterns(path)[0].skills == ("na.a.a", "na.b.b")


# --- the rows pushed to the database ----------------------------------------

def test_database_rows_carry_lists_as_lists():
    from scripts.db_push_taxonomy import error_rows, skill_rows
    taxonomy = load_taxonomy()
    rows = {r["skill_id"]: r for r in skill_rows(taxonomy)}
    assert isinstance(rows["na.factor.dos"]["prerequisites"], list)
    assert rows["na.directed.order"]["foundation"] is None
    assert all(isinstance(r["skills"], list) for r in error_rows(taxonomy))
