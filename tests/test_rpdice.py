"""The RPDICE standard: the rubric, the analysis checks, the golden set, the score."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.analyzer import (AnalysisPayload, AnalysisResult, AnalysisRun, build_prompt,
                          check_payload, export_analysis_json, load_analysis,
                          render_analysis_markdown, repair_drivers)
from app.analysis_store import analysis_rows, push_analysis
from app.paths import RPDICE_GOLD_CSV
from app.rpdice import (DIMENSIONS, LEVELS, MAX_LEVEL, Dimension, GoldRating,
                        QuestionAnalysis, RpdiceProfile, Strategy, drivers_of,
                        method_cues_in, profile_summary, read_gold, render_scorecard,
                        rubric_text, score_against_gold, validate_analysis, validate_gold)
from app.taxonomy import load_taxonomy
from tests.test_supabase_store import FakeClient, make_result


TAX = load_taxonomy()


def profile(**levels):
    dims = {d: Dimension(level=levels.get(d, 0),
                         evidence=[f"{d} evidence"] if levels.get(d, 0) else [])
            for d in DIMENSIONS}
    return RpdiceProfile(**dims)


def analysis(qid="4(a)", skills=("na.factor.recognise-square", "na.factor.dos"),
             errors=("err.dos.as-square-of-difference",), levels=None, **kw):
    levels = levels or dict(R=2, P=1, D=1, I=1, C=1, E=2)
    strategy = Strategy(strategy_name="DOS", steps=["see", "apply"], skills=list(skills),
                        rpdice=profile(**levels), is_primary=True)
    defaults = dict(source_question_id=qid, skill_family="Factorisation",
                    atomic_skills=list(skills), strategies=[strategy],
                    possible_errors=list(errors), difficulty_drivers=drivers_of(levels),
                    confidence=0.9)
    defaults.update(kw)
    return QuestionAnalysis(**defaults)


# --- the standard itself ----------------------------------------------------

def test_every_dimension_has_four_levels_with_distinct_wording():
    for d in DIMENSIONS:
        assert set(LEVELS[d]) == {0, 1, 2, 3}
        assert len({LEVELS[d][n] for n in range(4)}) == 4


def test_the_prompt_carries_the_rubric_and_the_taxonomy():
    text = rubric_text()
    assert "R = Recognition" in text and "E = Error Exposure" in text
    assert "  3: " in text
    prompt = build_prompt(make_result(), TAX)
    assert "{RUBRIC}" not in prompt and "{FORM}" not in prompt
    assert "na.factor.dos |" in prompt and "err.dos.as-square-of-difference |" in prompt
    assert '"source_question_id": "2(a)"' in prompt
    assert "Form 4 student" in prompt


def test_drivers_are_the_dimensions_at_two_or_above():
    assert drivers_of(dict(R=2, P=1, D=0, I=3, C=1, E=2)) == ["R", "I", "E"]
    assert drivers_of(dict(R=1, P=1, D=1, I=1, C=1, E=1)) == []


def test_profile_summary_is_compact():
    assert profile_summary(dict(R=2, P=1, D=0, I=1, C=2, E=2)) == "R2 P1 D0 I1 C2 E2"


@pytest.mark.parametrize("text,found", [
    ("利用二次公式解 5x² − 9x − 2 = 0。", True),
    ("利用配方法，求頂點坐標。", True),
    ("利用 (a) 的結果，解方程。", True),
    ("Hence, or otherwise, solve the equation.", True),
    ("由此求 k。", True),
    ("Use the quadratic formula to solve it.", True),
    ("解一元二次方程 x − 6x² − 4 = 0。", False),
    ("求該圓的方程。", False),
])
def test_method_cues_are_found_only_when_printed(text, found):
    assert bool(method_cues_in(text)) is found


# --- checking an analysis ---------------------------------------------------

def codes(a, text="因式分解 9a² − 25"):
    return sorted(i.issue_code for i in validate_analysis(a, text, TAX))


def test_a_sound_analysis_has_no_issues():
    assert codes(analysis()) == []


def test_levels_outside_the_scale_are_rejected():
    bad = analysis(levels=dict(R=4, P=1, D=1, I=1, C=1, E=2))
    assert "RPDICE_LEVEL_OUT_OF_RANGE" in codes(bad)


def test_a_level_above_zero_needs_evidence():
    a = analysis()
    a.strategies[0].rpdice.R.evidence = []
    assert "RPDICE_EVIDENCE_MISSING" in codes(a)


def test_a_level_of_zero_needs_no_evidence():
    assert codes(analysis(levels=dict(R=0, P=1, D=1, I=1, C=1, E=2))) == []


def test_an_invented_skill_is_an_error_but_a_proposal_is_fine():
    assert "SKILL_UNKNOWN" in codes(analysis(skills=("na.made.up",), errors=()))
    fine = analysis(proposed_skills=["a skill we do not have yet"])
    assert "SKILL_UNKNOWN" not in codes(fine)


def test_an_error_must_belong_to_a_listed_skill():
    a = analysis(errors=("err.trig.calculator-mode",))
    assert "ERROR_NOT_OF_SKILL" in codes(a)
    assert "ERROR_UNKNOWN" in codes(analysis(errors=("err.nope.nope",)))


def test_a_cue_caps_decision_at_one():
    a = analysis(levels=dict(R=1, P=1, D=2, I=1, C=1, E=2))
    assert "DECISION_IGNORES_CUE" in codes(a, "利用二次公式解 5x² − 9x − 2 = 0。")
    assert "DECISION_IGNORES_CUE" not in codes(a, "解 5x² − 9x − 2 = 0。")


def test_a_cue_must_be_copied_from_the_text():
    a = analysis(method_cues=["use the formula"])
    assert "METHOD_CUE_NOT_IN_TEXT" in codes(a)


def test_drivers_that_disagree_with_the_levels_are_flagged_and_repairable():
    a = analysis(difficulty_drivers=["C"])
    assert "DRIVERS_MISMATCH" in codes(a)
    payload = AnalysisPayload(analyses=[a])
    assert repair_drivers(payload) == 1
    assert payload.analyses[0].difficulty_drivers == ["R", "E"]


def test_integration_must_match_the_units_of_the_skills():
    one_unit_high_i = analysis(levels=dict(R=1, P=1, D=1, I=2, C=1, E=1))
    assert "INTEGRATION_INCONSISTENT" in codes(one_unit_high_i)
    two_skills_zero_i = analysis(levels=dict(R=1, P=1, D=1, I=0, C=1, E=1))
    assert "INTEGRATION_INCONSISTENT" in codes(two_skills_zero_i)


def test_exactly_one_primary_strategy():
    a = analysis()
    a.strategies.append(a.strategies[0].model_copy())
    assert "PRIMARY_STRATEGY_COUNT" in codes(a)


def test_empirical_difficulty_must_stay_null():
    assert "EMPIRICAL_NOT_NULL" in codes(analysis(empirical_difficulty=0.7))


def test_the_payload_is_checked_against_the_paper():
    result = make_result()            # questions 1 and 2(a)
    payload = AnalysisPayload(analyses=[analysis(qid="1"), analysis(qid="9")])
    found = {i.issue_code for i in check_payload(payload, result, TAX)}
    assert {"QUESTION_NOT_ANALYSED", "ANALYSIS_FOR_UNKNOWN_QUESTION"} <= found


# --- the golden set ---------------------------------------------------------

def test_the_shipped_golden_set_is_valid():
    gold = read_gold(RPDICE_GOLD_CSV)
    assert len(gold) >= 25
    assert validate_gold(gold, TAX) == []
    assert all(g.status == "draft" for g in gold)      # nothing confirmed yet


def test_gold_faults_are_named():
    bad = GoldRating("k:1", "p", "1", ("na.nope.x",), dict(R=5, P=0, D=0, I=0, C=0, E=0),
                     ("err.nope.y",), "me", "maybe")
    problems = validate_gold([bad, bad], TAX)
    assert any("more than once" in p for p in problems)
    assert any("R = 5" in p for p in problems)
    assert any("skill na.nope.x" in p for p in problems)
    assert any("status" in p for p in problems)


# --- scoring ----------------------------------------------------------------

def test_perfect_agreement_scores_one():
    gold = read_gold(RPDICE_GOLD_CSV)[:3]
    analyses = {g.question_key: analysis(qid=g.source_question_id, skills=g.skills,
                                          errors=g.errors, levels=g.levels) for g in gold}
    card = score_against_gold(analyses, gold)
    assert card.compared == 3 and not card.missing
    assert all(card.dimensions[d].exact_rate == 1.0 for d in DIMENSIONS)
    assert card.mean_skill_overlap == 1.0


def test_bias_and_missing_are_reported():
    gold = [GoldRating("k:1", "p", "1", ("na.factor.dos",), dict(R=1, P=1, D=1, I=0, C=1, E=1),
                       (), "me", "draft"),
            GoldRating("k:2", "p", "2", ("na.factor.dos",), dict(R=1, P=1, D=1, I=0, C=1, E=1),
                       (), "me", "draft")]
    over = analysis(qid="1", levels=dict(R=3, P=1, D=1, I=0, C=1, E=1), errors=())
    card = score_against_gold({"k:1": over}, gold)
    assert card.missing == ["k:2"]
    assert card.dimensions["R"].mean_bias == 2 and card.dimensions["R"].within_one_rate == 0
    text = render_scorecard(card)
    assert "| R Recognition | 0% | 0% | 2.00 | +2.00 |" in text
    assert "k:2" in text


# --- saving and the database rows -------------------------------------------

def make_analysis_result(**kw):
    defaults = dict(file_name="p.pdf", sha256="a" * 64, extraction_run_id="run1", level="F4",
                    run=AnalysisRun(run_id="an1", analysed_at="t", analyzer_version="RPDICE_v1",
                                    model="m", prompt_sha256="abc123abc123"),
                    analyses=[analysis(qid="1"), analysis(qid="2(a)")])
    defaults.update(kw)
    return AnalysisResult(**defaults)


def test_an_analysis_round_trips_through_json(tmp_path):
    path = export_analysis_json(make_analysis_result(), tmp_path / "a.json")
    back = load_analysis(path)
    assert back.by_key()["aaaaaaaaaaaa:1"].levels() == dict(R=2, P=1, D=1, I=1, C=1, E=2)
    assert json.loads(path.read_text())["analyses"][0]["empirical_difficulty"] is None


def test_the_report_shows_each_profile():
    text = render_analysis_markdown(make_analysis_result(), TAX)
    assert "`R2 P1 D1 I1 C1 E2`" in text and "Factorise a difference of two squares" in text


def test_rows_hang_off_the_question_key_and_supersede_older_runs():
    rows = analysis_rows(make_analysis_result())
    assert [r["question_key"] for r in rows] == ["aaaaaaaaaaaa:1", "aaaaaaaaaaaa:2(a)"]
    assert rows[0]["rpdice"] == dict(R=2, P=1, D=1, I=1, C=1, E=2)
    assert rows[0]["difficulty_drivers"] == ["R", "E"]

    client = FakeClient()
    client.rows["question_analyses"] = []
    push_analysis(client, make_analysis_result(run=AnalysisRun(
        run_id="an1", analysed_at="t", analyzer_version="v", model="m")))
    push_analysis(client, make_analysis_result(run=AnalysisRun(
        run_id="an2", analysed_at="t", analyzer_version="v", model="m")))
    current = {(r["question_key"], r["analysis_run_id"]) for r in client.rows["question_analyses"]
               if r["is_current"]}
    assert current == {("aaaaaaaaaaaa:1", "an2"), ("aaaaaaaaaaaa:2(a)", "an2")}
