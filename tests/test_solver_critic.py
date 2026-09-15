"""Strategy identity, the Solver's checks, the Critic's normalisation and statuses."""

from __future__ import annotations

import json

import pytest

from app import analyzer as analyzer_module
from app.analyzer import AnalysisResult, assign_strategy_ids, render_analysis_markdown
from app.critic import (Critic, CriticIssue, CriticPayload, apply_status, build_critic_prompt,
                        critique, normalise_issues)
from app.rpdice import (AnalysisPayload, StrategySolution, strategy_id_for, validate_analysis)
from app.solver import (SolverPayload, Solver, answers_match, build_solver_prompt,
                        check_solutions, normalise_answer)
from app.taxonomy import load_taxonomy
from scripts import critique_rpdice
from tests.test_rpdice import analysis, make_analysis_result
from tests.test_supabase_store import make_result


TAX = load_taxonomy()


# --- strategy identity ------------------------------------------------------

def test_strategy_ids_are_stable_and_ignore_spelling_but_not_skills():
    a = strategy_id_for("Difference of two squares", ["na.factor.dos", "na.factor.recognise-square"])
    b = strategy_id_for("  difference  of two SQUARES ", ["na.factor.recognise-square", "na.factor.dos"])
    c = strategy_id_for("Difference of two squares", ["na.factor.dos"])
    assert a == b and len(a) == 12
    assert a != c


def test_the_analyzer_assigns_ids_and_overwrites_what_the_model_said():
    a = analysis()
    a.strategies[0].strategy_id, a.strategies[0].source, a.strategies[0].status = "x", "student", "confirmed"
    payload = AnalysisPayload(analyses=[a])
    assign_strategy_ids(payload)
    s = payload.analyses[0].strategies[0]
    assert s.strategy_id == strategy_id_for("DOS", s.skills)
    assert (s.source, s.status) == ("analyzer", "proposed")


def test_two_strategies_that_are_the_same_method_are_flagged():
    a = analysis()
    twin = a.strategies[0].model_copy(deep=True)
    twin.is_primary = False
    a.strategies.append(twin)
    assign_strategy_ids(AnalysisPayload(analyses=[a]))
    codes = [i.issue_code for i in validate_analysis(a, "因式分解 9a² − 25", TAX)]
    assert "DUPLICATE_STRATEGY" in codes
    a.strategies[0].status = "maybe"
    assert "STRATEGY_FIELDS_INVALID" in [i.issue_code for i in validate_analysis(a, "x", TAX)]


# --- answers ----------------------------------------------------------------

@pytest.mark.parametrize("given,reference,expected", [
    ("1024", "1024", True),
    ("x = 1024", "1024", True),
    ("B", "(B)", True),
    ("B (1024)", "B", True),
    ("B (1024)", "1024", True),
    ("3/4", "0.75", True),
    ("−5", "-5", True),
    ("1024", "896", False),
    ("A", "B", False),
    ("1024", None, None),
    (None, "1024", None),
])
def test_answers_are_compared_after_normalising(given, reference, expected):
    assert answers_match(given, reference) is expected


def test_normalise_answer_forms():
    assert normalise_answer("(C).") == "C"
    assert normalise_answer("y = 2x + 1") == "2x+1"
    assert normalise_answer("  ") is None


# --- the Solver ---------------------------------------------------------------

def reviewed():
    """An extraction with answers and its analysis, ids assigned."""
    extraction = make_result()
    extraction.document.questions[0].answer = "x = 3"
    result = make_analysis_result(analyses=[analysis(qid="1"), analysis(qid="2(a)")])
    assign_strategy_ids(AnalysisPayload(analyses=result.analyses))
    return extraction, result


def solution(qid, sid, answer="x = 3", reached=True, **kw):
    return StrategySolution(source_question_id=qid, strategy_id=sid, final_answer=answer,
                            worked_steps=["a", "b"], reached_answer=reached, **kw)


def test_the_solver_prompt_carries_the_pairs_and_the_reference_answer():
    extraction, result = reviewed()
    prompt = build_solver_prompt(extraction, result, ["1"])
    assert '"reference_answer": "x = 3"' in prompt
    assert result.analyses[0].strategies[0].strategy_id in prompt
    assert '"2(a)"' not in prompt                       # batching by question id


def test_solver_checks_name_the_missing_the_failed_and_the_wrong():
    extraction, result = reviewed()
    sid1 = result.analyses[0].strategies[0].strategy_id
    sid2 = result.analyses[1].strategies[0].strategy_id
    fine = [solution("1", sid1), solution("2(a)", sid2, answer="B")]
    assert check_solutions(result, extraction, fine) == []

    wrong = [solution("1", sid1, answer="x = 4"), solution("2(a)", sid2, reached=False, notes="stuck")]
    codes = {i.issue_code for i in check_solutions(result, extraction, wrong)}
    assert codes == {"ANSWER_MISMATCH", "STRATEGY_DOES_NOT_SOLVE"}

    codes = {i.issue_code for i in check_solutions(result, extraction, [solution("1", "nope")])}
    assert codes == {"SOLUTION_MISSING", "SOLUTION_FOR_UNKNOWN_STRATEGY"}


def test_strategies_that_disagree_with_each_other_are_flagged():
    extraction, result = reviewed()
    second = result.analyses[0].strategies[0].model_copy(deep=True)
    second.strategy_name, second.is_primary, second.strategy_id = "other", False, "abc123abc123"
    result.analyses[0].strategies.append(second)
    sols = [solution("1", result.analyses[0].strategies[0].strategy_id, answer="3"),
            solution("1", "abc123abc123", answer="4"),
            solution("2(a)", result.analyses[1].strategies[0].strategy_id, answer="B")]
    codes = [i.issue_code for i in check_solutions(result, extraction, sols)]
    assert "STRATEGIES_DISAGREE" in codes and "ANSWER_MISMATCH" in codes


class FakeGemini:
    last_usage = {"input_tokens": 10, "output_tokens": 5}
    model = "fake-critic"

    def __init__(self, payloads):
        self.payloads, self.prompts = list(payloads), []

    def generate_json(self, prompt, schema):
        self.prompts.append(prompt)
        payload = self.payloads.pop(0)
        assert isinstance(payload, schema)
        return payload


def test_the_solver_batches_questions_and_adds_up_usage(monkeypatch):
    from app import solver as solver_module
    monkeypatch.setattr(solver_module, "SOLVER_BATCH", 1)
    extraction, result = reviewed()
    sid1, sid2 = (a.strategies[0].strategy_id for a in result.analyses)
    gemini = FakeGemini([SolverPayload(solutions=[solution("1", sid1)]),
                         SolverPayload(solutions=[solution("2(a)", sid2, answer="B")])])
    built = Solver.__new__(Solver)
    built.gemini, built.usage = gemini, {"input_tokens": 0, "output_tokens": 0}
    got = built.solve(extraction, result)
    assert [s.strategy_id for s in got] == [sid1, sid2]
    assert len(gemini.prompts) == 2 and built.usage == {"input_tokens": 20, "output_tokens": 10}


# --- the Critic ---------------------------------------------------------------

def test_critic_issues_are_normalised_to_known_codes_questions_and_severities():
    _, result = reviewed()
    sid = result.analyses[0].strategies[0].strategy_id
    raw = [CriticIssue(source_question_id="1", strategy_id=sid, issue_code="level_overrated",
                       severity="HIGH", message="R should be 1"),
           CriticIssue(source_question_id="1", issue_code="SOMETHING_NEW", severity="urgent",
                       message="odd"),
           CriticIssue(source_question_id="9", issue_code="SKILL_MISSING", message="not a question")]
    issues = normalise_issues(raw, result)
    assert [i.issue_code for i in issues] == ["LEVEL_OVERRATED", "CRITIC_OTHER"]
    assert issues[0].severity == "high" and issues[0].message == f"1: [{sid}] R should be 1"
    assert issues[1].severity == "medium"


def test_statuses_follow_the_solver_and_the_critic():
    _, result = reviewed()
    sid1, sid2 = (a.strategies[0].strategy_id for a in result.analyses)
    sols = [solution("1", sid1), solution("2(a)", sid2, reached=False)]
    counts = apply_status(result, sols, [])
    assert counts == {"confirmed": 1, "rejected": 1, "proposed": 0}
    assert result.analyses[0].strategies[0].status == "confirmed"
    assert result.analyses[1].strategies[0].status == "rejected"
    # a high Critic issue against the strategy holds it back to proposed
    from app.schemas import ValidationIssue
    high = ValidationIssue(issue_code="LEVEL_OVERRATED", severity="high",
                           message=f"1: [{sid1}] R is 1", source_question_id="1")
    assert apply_status(result, sols, [high])["proposed"] == 1
    # no solution at all: proposed
    assert apply_status(result, [], [])["proposed"] == 2


def test_the_critic_prompt_is_independent_and_carries_analysis_and_solver_output():
    extraction, result = reviewed()
    sid = result.analyses[0].strategies[0].strategy_id
    prompt = build_critic_prompt(extraction, result, [solution("1", sid)], ["1"])
    assert "R = Recognition" in prompt and "{RUBRIC}" not in prompt
    assert '"final_answer": "x = 3"' in prompt and '"strategy_name": "DOS"' in prompt
    assert "empirical_difficulty" not in prompt


def test_critique_runs_solver_then_critic_and_records_the_run():
    extraction, result = reviewed()
    sid1, sid2 = (a.strategies[0].strategy_id for a in result.analyses)
    solver = Solver.__new__(Solver)
    solver.gemini = FakeGemini([SolverPayload(solutions=[solution("1", sid1),
                                                         solution("2(a)", sid2, answer="B")])])
    solver.usage = {"input_tokens": 0, "output_tokens": 0}
    critic = Critic.__new__(Critic)
    critic.gemini = FakeGemini([CriticPayload(issues=[
        CriticIssue(source_question_id="2(a)", strategy_id=sid2, issue_code="ERROR_MISSING",
                    severity="medium", message="err.factor.incomplete is not listed")])])
    critic.usage = {"input_tokens": 0, "output_tokens": 0}

    class S:
        gemini_critic_model = "c"
    critic.settings = S()

    critique(extraction, result, solver, critic)
    assert len(result.solutions) == 2
    assert [i.issue_code for i in result.critic_issues] == ["ERROR_MISSING"]
    assert result.critic.model == "fake-critic" and result.critic.input_tokens == 20
    assert len(result.critic.solver_prompt_sha256) == 12
    assert {s.status for a in result.analyses for s in a.strategies} == {"confirmed"}
    text = render_analysis_markdown(result, TAX)
    assert "Solver: reached **x = 3**" in text and "## Critic" in text and "confirmed" in text
    back = AnalysisResult.model_validate(json.loads(json.dumps(result.model_dump())))
    assert back.critic.run_id == result.critic.run_id


# --- the script ---------------------------------------------------------------

def test_critique_rpdice_pairs_an_analysis_with_its_extraction(tmp_path, monkeypatch, capsys):
    from app.json_exporter import export_extraction_json
    from app.analyzer import export_analysis_json
    extraction, result = reviewed()
    analyses, extracted = tmp_path / "analyses", tmp_path / "extracted"
    analyses.mkdir(); extracted.mkdir()
    export_extraction_json(extraction, extracted / "p-aaaaaaaaaaaa.json")
    export_analysis_json(result, analyses / "p-aaaaaaaaaaaa.json")
    monkeypatch.setattr(critique_rpdice, "ANALYSES_DIR", analyses)
    monkeypatch.setattr(critique_rpdice, "EXTRACTED_DIR", extracted)
    monkeypatch.setattr(critique_rpdice, "_client", lambda: None)
    sid1, sid2 = (a.strategies[0].strategy_id for a in result.analyses)

    def fake_solver():
        s = Solver.__new__(Solver)
        s.gemini = FakeGemini([SolverPayload(solutions=[solution("1", sid1),
                                                        solution("2(a)", sid2, answer="B")])])
        s.usage = {"input_tokens": 0, "output_tokens": 0}
        return s

    def fake_critic():
        c = Critic.__new__(Critic)
        c.gemini = FakeGemini([CriticPayload(issues=[])])
        c.usage = {"input_tokens": 0, "output_tokens": 0}
        return c

    monkeypatch.setattr(critique_rpdice, "Solver", fake_solver)
    monkeypatch.setattr(critique_rpdice, "Critic", fake_critic)

    assert critique_rpdice.main([]) == 0
    saved = json.loads((analyses / "p-aaaaaaaaaaaa.json").read_text())
    assert saved["critic"] is not None and len(saved["solutions"]) == 2
    assert "Solver: reached" in (analyses / "p-aaaaaaaaaaaa.md").read_text()
    assert "2 confirmed" in capsys.readouterr().out
    # a second run without --again leaves it alone: no Solver is even built
    monkeypatch.setattr(critique_rpdice, "Solver", lambda: (_ for _ in ()).throw(AssertionError))
    assert critique_rpdice.main([]) == 0
    assert json.loads((analyses / "p-aaaaaaaaaaaa.json").read_text())["critic"]["run_id"] == \
        saved["critic"]["run_id"]
