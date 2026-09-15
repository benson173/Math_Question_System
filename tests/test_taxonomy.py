"""The skill and error vocabularies: valid as shipped, and checked when edited."""

from __future__ import annotations



import pytest

from app.taxonomy import (
    GuideObjective,
    ErrorPattern,
    Skill,
    load_taxonomy,
    read_error_patterns,
    read_guide_objectives,
    read_skills,
    validate,
)


# --- the shipped files ------------------------------------------------------

def test_the_shipped_taxonomy_is_valid():
    taxonomy = load_taxonomy()
    assert len(taxonomy.skills) > 300
    assert len(taxonomy.errors) > 60
    assert len(taxonomy.objectives) > 300


def test_every_assessed_guide_objective_has_a_skill_and_every_skill_a_reference():
    taxonomy = load_taxonomy()
    assert taxonomy.uncovered_objectives() == []
    for s in taxonomy.skills.values():
        if s.strand in ("na", "ms", "dh", "fl"):
            assert s.guide_ref, s.skill_id
    # the flags come from the Guide: unit 3 (exp / log) is Non-foundation throughout,
    # sequences too, while the whole of KS3 directed numbers is Foundation
    assert taxonomy.skills["na.log.laws"].foundation == "non-foundation"
    assert taxonomy.skills["na.seq.as-term"].foundation == "non-foundation"
    assert taxonomy.skills["na.directed.add-sub"].foundation == "foundation"
    assert taxonomy.skills["ms.solid.euler"].foundation == "enrichment"
    assert taxonomy.skills["na.quad.solve-factor"].guide_ref == ("CP-1.1",)
    assert taxonomy.objectives["CP-1.7"].status == "non-foundation"
    assert taxonomy.objectives["KS3-17.5"].status == "enrichment"
    assert [s.skill_id for s in taxonomy.skills_for_objective("CP-14.8")] == \
        ["ms.trig.3d-three-perpendiculars"]


def test_a_skill_outside_the_guide_is_marked_ext():
    taxonomy = load_taxonomy()
    outside = taxonomy.skills["m1.geo.probability"]          # no geometric distribution in M1
    assert outside.guide_ref == ("ext",) and not outside.in_guide


def test_every_strand_form_and_unit_is_represented():
    taxonomy = load_taxonomy()
    assert {s.strand for s in taxonomy.skills.values()} == {"na", "ms", "dh", "fl",
                                                            "m1", "m2"}
    assert {s.form for s in taxonomy.skills.values()} == {"F1", "F2", "F3", "F4", "F5", "F6"}
    units = {s.unit for s in taxonomy.skills.values()}
    for unit in ("Quadratic equations in one unknown", "Basic properties of circles",
                 "Permutations and combinations", "Measures of dispersion", "Factorisation"):
        assert unit in units          # Guide unit names, except our own cross-cutting ones


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
    assert taxonomy.skills_in_unit("Loci")
    assert taxonomy.errors_for_skill("na.log.laws")


def test_general_errors_belong_to_every_skill_of_their_scope():
    taxonomy = load_taxonomy()
    for_parallel = {e.error_id for e in taxonomy.errors_for_skill("ms.angles.parallel-prove")}
    assert "err.geo.assumes-from-diagram" in for_parallel      # ms.*
    assert "err.trig.rounding-early" in for_parallel           # *
    for_log = {e.error_id for e in taxonomy.errors_for_skill("na.log.laws")}
    assert "err.geo.assumes-from-diagram" not in for_log
    assert taxonomy.errors["err.geo.assumes-from-diagram"].is_general


def test_an_error_fits_a_listed_skill_or_one_it_rests_on():
    taxonomy = load_taxonomy()
    # the converse of Pythagoras rests on Pythagoras' theorem itself
    assert taxonomy.error_fits("err.pythag.wrong-hypotenuse", ["ms.pythag.converse"])
    assert not taxonomy.error_fits("err.pythag.wrong-hypotenuse", ["ms.angles.basic"])
    # a general error fits anything
    assert taxonomy.error_fits("err.eq.sign-transposing", ["na.simeq.elimination"])
    assert taxonomy.error_fits("err.eq.sign-transposing", ["ms.angles.basic"])
    assert not taxonomy.error_fits("err.trig.calculator-mode", ["na.factor.dos"])
    assert not taxonomy.error_fits("err.trig.calculator-mode", ["na.made.up"])


def test_a_wrong_strand_prefix_maps_to_the_one_skill_it_can_mean():
    taxonomy = load_taxonomy()
    assert taxonomy.unique_skill_for("ms.lineq.solve") == "na.lineq.solve"
    assert taxonomy.unique_skill_for("na.lineq.solve") is None       # already right
    assert taxonomy.unique_skill_for("na.made.up") is None
    assert taxonomy.unique_skill_for("lineq.solve") is None


# --- what the validator catches ---------------------------------------------

def skill(skill_id="na.x.y", form="F4", foundation="foundation", prerequisites=(),
          guide_ref=("CP-1.1",), **kw):
    defaults = dict(skill_id=skill_id, strand=skill_id.split(".")[0], unit="U",
                    name_en="n", name_zh="名", form=form, foundation=foundation,
                    prerequisites=tuple(prerequisites), guide_ref=tuple(guide_ref))
    defaults.update(kw)
    return Skill(**defaults)


def error(error_id="err.x.y", skills=("na.x.y",)):
    return ErrorPattern(error_id=error_id, name_en="n", name_zh="名", skills=tuple(skills))


def test_a_clean_pair_has_no_problems():
    assert validate([skill()], [error()]) == []


def test_wildcard_error_scopes_are_valid_but_only_for_real_strands():
    assert validate([skill()], [error(skills=("*",))]) == []
    assert validate([skill()], [error(skills=("na.*",))]) == []
    assert any("does not exist" in p for p in validate([skill()], [error(skills=("xx.*",))]))
    assert any("does not exist" in p for p in validate([skill()], [error(skills=("na.x.*",))]))


@pytest.mark.parametrize("bad,expected", [
    ([skill(), skill()], "appears more than once"),
    ([skill(skill_id="bad id", strand="na")], "not <strand>.<unit>.<slug>"),
    ([skill(skill_id="ms.x.y", strand="na")], "says strand"),
    ([skill(form="F7")], "not F1-F6"),
    ([skill(form="F4", foundation=None)], "no foundation flag"),
    ([skill(form="F2", foundation=None)], "no foundation flag"),          # KS3 is flagged too
    ([skill(skill_id="m1.x.y", foundation="foundation", guide_ref=("M1-1.1",))], "does not apply"),
    ([skill(guide_ref=())], "has no guide_ref"),
    ([skill(guide_ref=("CP1.1",))], "not <part>-<n.m>"),
    ([skill(prerequisites=("na.nope.nope",))], "does not exist"),
    ([skill(prerequisites=("na.x.y",))], "lists itself"),
    ([skill(name_zh="")], "missing an English or Chinese name"),
])
def test_each_skill_fault_is_named(bad, expected):
    problems = validate(bad, [])
    assert any(expected in p for p in problems), problems


def objective(ref="CP-1.1", status="foundation"):
    part, obj = ref.split("-")
    return GuideObjective(ref=ref, part=part, strand="s", unit_no=obj.split(".")[0], unit="u",
                          text="t", status=status)


def test_with_the_guide_a_reference_must_exist_and_the_flag_must_agree():
    guide = [objective("CP-1.1"), objective("CP-1.7", "non-foundation"),
             objective("KS3-17.5", "enrichment")]
    assert validate([skill()], [], guide) == []
    assert any("not in guide_objectives" in p for p in validate([skill(guide_ref=("CP-9.9",))], [], guide))
    wrong = skill(guide_ref=("CP-1.7",))                    # flagged F, objective is N
    assert any("Guide objectives say non-foundation" in p for p in validate([wrong], [], guide))
    assert validate([skill(guide_ref=("CP-1.7",), foundation="non-foundation")], [], guide) == []
    assert validate([skill(guide_ref=("KS3-17.5",), foundation="enrichment")], [], guide) == []
    # a skill touching a Foundation objective and a Non-foundation one is Foundation
    assert validate([skill(guide_ref=("CP-1.1", "CP-1.7"))], [], guide) == []
    # ext skills carry no flag and are not checked against the Guide
    assert validate([skill(guide_ref=("ext",), foundation=None)], [], guide) == []


def test_the_shipped_objectives_file_reads():
    objectives = read_guide_objectives()
    parts = {o.part for o in objectives}
    assert parts == {"KS3", "CP", "M1", "M2"}
    assert any(o.ref == "CP-19" for o in objectives)         # Further Learning Unit


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
    assert rows["na.directed.order"]["foundation"] == "foundation"
    assert rows["m1.geo.probability"]["foundation"] is None
    assert rows["na.factor.dos"]["guide_ref"] == ["KS3-12.3"]
    assert all(isinstance(r["skills"], list) for r in error_rows(taxonomy))
