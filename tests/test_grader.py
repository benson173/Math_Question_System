"""The Grader: reading one handwritten page against the question's analysis."""

from __future__ import annotations

import json

import pytest

from app.analyzer import assign_strategy_ids
from app.grader import (ErrorObservation, GradedAttempt, Grader, GraderPayload, attempt_path,
                        build_grader_prompt, decide, export_attempt, find_question,
                        question_skills, render_attempt_markdown)
from app.attempt_store import attempt_row
from app.rpdice import AnalysisPayload
from app.taxonomy import load_taxonomy
from scripts import grade_answer
from tests.test_rpdice import analysis, make_analysis_result
from tests.test_supabase_store import make_result


TAX = load_taxonomy()
Q24_SKILLS = ("na.quad.solve-factor", "na.func.vertex-form", "ms.mensur.rect-tri-area")


def q24():
    """The real page: Q24 of 2526_2nd_S4MATH2, as the student wrote it."""
    extraction = make_result()
    q = extraction.document.questions[0]
    q.source_question_id = "24"
    q.question_text = "y = −2x² + 28x + 30 的圖像與 x 軸相交於 A 和 B 兩點。求 ΔAPB 的最大面積。"
    q.question_type, q.options, q.answer = "multiple_choice", ["128", "896", "960", "1024"], "D"
    result = make_analysis_result(analyses=[analysis(qid="24", skills=Q24_SKILLS, errors=("err.quad.vertex-sign",),
                                                     levels=dict(R=2, P=2, D=1, I=2, C=2, E=1))])
    result.analyses[0].strategies[0].strategy_name = "Base from intercepts, height from vertex"
    assign_strategy_ids(AnalysisPayload(analyses=result.analyses))
    return extraction, result


def reading_of_the_page(sid):
    return GraderPayload(
        transcription=["頂點的 x 坐標", "x = 28 / 2(-2) = 7", "y = 2(7)^2 + 28(7) + 30", "= -98 + 196 + 30",
                       "= 128", "∴ a = -2 < 0", "y max = 128", "最大面積: [△APB]max = 1/2 × 16 × 128",
                       "= 8 × 128", "= 1024"],
        final_answer="1024", option_chosen="D", strategy_id_matched=sid,
        strategy_description="vertex by -b/2a, y_max, then half base times height with base 16 written down",
        skills_evidenced=["na.func.vertex-form", "ms.mensur.rect-tri-area", "na.formula.substitute"],
        errors_observed=[ErrorObservation(error_id="err.quad.vertex-sign", kind="slip",
                                          description="wrote 28/2(-2) = 7 without the minus, result right"),
                         ErrorObservation(error_id=None, kind="slip",
                                          description="wrote 2(7)^2 for -2(7)^2 but evaluated -98")],
        unclear=[], confidence=0.92)


# --- prompt -------------------------------------------------------------------

def test_the_prompt_carries_question_strategies_skills_and_errors_but_not_the_answer():
    extraction, result = q24()
    q, a = find_question(extraction, "24"), result.analyses[0]
    prompt = build_grader_prompt(q, a, TAX)
    assert "圖像與 x 軸相交" in prompt and a.strategies[0].strategy_id in prompt
    assert "na.quad.solve-factor |" in prompt and "na.factor.cross |" in prompt      # a prerequisite
    assert "err.quad.vertex-sign |" in prompt
    assert '"D"' not in prompt and "reference" not in prompt.lower()
    assert "Copy slips faithfully" in prompt
    with pytest.raises(KeyError):
        find_question(extraction, "99")


def test_question_skills_include_prerequisites_once():
    _, result = q24()
    skills = question_skills(result.analyses[0], TAX)
    assert skills[:3] == list(Q24_SKILLS) and len(skills) == len(set(skills))
    assert "na.factor.cross" in skills


# --- deciding -----------------------------------------------------------------

def test_the_real_page_is_correct_matched_and_shows_a_gap():
    extraction, result = q24()
    q, a = find_question(extraction, "24"), result.analyses[0]
    sid = a.strategies[0].strategy_id
    verdict = decide(reading_of_the_page(sid), q, a, TAX)
    assert verdict["is_correct"] is True and verdict["reference_answer"] == "D"
    assert verdict["strategy_match"] == "listed" and verdict["strategy_id"] == sid
    assert verdict["skills_not_evidenced"] == ["na.quad.solve-factor"]     # base 16 with no roots
    assert verdict["error_ids"] == ["err.quad.vertex-sign"]
    assert len(verdict["slips"]) == 2 and verdict["misconceptions"] == []
    assert verdict["needs_human"] is False


def test_a_letter_is_marked_against_a_value_and_a_value_against_a_letter():
    extraction, result = q24()
    q, a = find_question(extraction, "24"), result.analyses[0]
    q.answer = "1024"
    assert decide(GraderPayload(option_chosen="D", confidence=0.9), q, a, TAX)["is_correct"] is True
    assert decide(GraderPayload(option_chosen="B", confidence=0.9), q, a, TAX)["is_correct"] is False
    q.answer = "D"
    assert decide(GraderPayload(final_answer="1024", option_chosen="D", confidence=0.9), q, a, TAX)["is_correct"] is True
    q.answer = None
    v = decide(GraderPayload(option_chosen="D", confidence=0.9), q, a, TAX)
    assert v["is_correct"] is None and v["needs_human"] and "no reference" in v["review_reasons"][0]


def test_what_sends_a_page_to_a_person():
    extraction, result = q24()
    q, a = find_question(extraction, "24"), result.analyses[0]
    unread = GraderPayload(option_chosen="D", unclear=["line 3 digit"], confidence=0.9)
    assert "unreadable: line 3 digit" in decide(unread, q, a, TAX)["review_reasons"]
    shaky = GraderPayload(option_chosen="D", confidence=0.4)
    assert any("low confidence" in r for r in decide(shaky, q, a, TAX)["review_reasons"])
    other_route = GraderPayload(option_chosen="D", transcription=["..."], confidence=0.9,
                                strategy_description="differentiated y and set dy/dx = 0")
    v = decide(other_route, q, a, TAX)
    assert v["strategy_match"] == "new" and v["strategy_id"] is None
    assert v["skills_not_evidenced"] == list(Q24_SKILLS)          # measured against the primary
    wrong_idea = GraderPayload(option_chosen="D", confidence=0.9, errors_observed=[
        ErrorObservation(error_id="err.quad.vertex-sign", kind="misconception", description="x = -7 used")])
    assert "misconception" in " ".join(decide(wrong_idea, q, a, TAX)["review_reasons"])
    unknown_error = GraderPayload(option_chosen="D", confidence=0.9, errors_observed=[
        ErrorObservation(error_id="err.made.up", kind="slip", description="x")])
    assert decide(unknown_error, q, a, TAX)["error_ids"] == []


# --- running -----------------------------------------------------------------

class FakeGemini:
    last_usage = {"input_tokens": 500, "output_tokens": 80}
    model = "fake-vision"

    def __init__(self, payload):
        self.payload, self.calls = payload, []

    def generate_json(self, prompt, schema, images=None):
        self.calls.append((prompt, images))
        assert schema is GraderPayload
        return self.payload


def test_grade_sends_the_scan_and_writes_a_complete_attempt(tmp_path, monkeypatch):
    from app import grader as grader_module
    extraction, result = q24()
    sid = result.analyses[0].strategies[0].strategy_id
    scan = tmp_path / "wong.jpg"
    scan.write_bytes(b"\xff\xd8\xff fake jpeg")
    gemini = FakeGemini(reading_of_the_page(sid))
    built = Grader.__new__(Grader)
    built.gemini, built.taxonomy = gemini, TAX

    class S:
        gemini_extractor_model = "m"
    built.settings = S()

    attempt = built.grade(scan, "wong", extraction, result, "24")
    assert gemini.calls[0][1] == [(b"\xff\xd8\xff fake jpeg", "image/jpeg")]
    assert attempt.question_key == "aaaaaaaaaaaa:24" and attempt.is_correct is True
    assert attempt.strategy_id == sid and attempt.run.model == "fake-vision"
    assert attempt.run.input_tokens == 500 and len(attempt.scan_sha256) == 64

    monkeypatch.setattr(grader_module, "ATTEMPTS_DIR", tmp_path / "attempts")
    path = export_attempt(attempt, attempt_path(attempt))
    assert path.parent.name == "wong" and path.name.startswith("aaaaaaaaaaaa_24-")
    back = GradedAttempt.model_validate(json.loads(path.read_text()))
    assert back.reading.transcription[1] == "x = 28 / 2(-2) = 7"

    text = render_attempt_markdown(attempt, TAX, "wong.jpg")
    assert "**Verdict: correct**" in text and "![scan](wong.jpg)" in text
    assert "✗ not shown: Solve a quadratic equation by factorisation" in text
    assert "- slip: err.quad.vertex-sign: wrote 28/2(-2) = 7" in text

    row = attempt_row(attempt)
    assert row["answer_given"] == "D" and row["strategy_id"] == sid
    assert isinstance(row["skills_not_evidenced"], list) and row["needs_human"] is False

    (tmp_path / "x.txt").write_text("not a scan")
    with pytest.raises(ValueError):
        built.grade(tmp_path / "x.txt", "wong", extraction, result, "24")
    with pytest.raises(KeyError):
        built.grade(scan, "wong", extraction, result, "99")


def test_grade_answer_script_finds_the_paper_by_key_or_by_stem(tmp_path, monkeypatch, capsys):
    from app.json_exporter import export_extraction_json
    from app.analyzer import export_analysis_json
    from app import grader as grader_module
    extraction, result = q24()
    extracted, analyses = tmp_path / "extracted", tmp_path / "analyses"
    extracted.mkdir(); analyses.mkdir()
    export_extraction_json(extraction, extracted / "p-aaaaaaaaaaaa.json")
    export_analysis_json(result, analyses / "p-aaaaaaaaaaaa.json")
    monkeypatch.setattr(grade_answer, "EXTRACTED_DIR", extracted)
    monkeypatch.setattr(grade_answer, "ANALYSES_DIR", analyses)
    monkeypatch.setattr(grade_answer, "_client", lambda: None)
    monkeypatch.setattr(grader_module, "ATTEMPTS_DIR", tmp_path / "attempts")
    sid = result.analyses[0].strategies[0].strategy_id

    def fake_grader():
        g = Grader.__new__(Grader)
        g.gemini, g.taxonomy = FakeGemini(reading_of_the_page(sid)), TAX

        class S:
            gemini_extractor_model = "m"
        g.settings = S()
        return g
    monkeypatch.setattr(grade_answer, "Grader", fake_grader)
    scan = tmp_path / "wong.pdf"
    scan.write_bytes(b"%PDF fake")

    assert grade_answer.main([str(scan), "--student", "wong", "--question", "aaaaaaaaaaaa:24"]) == 0
    out = capsys.readouterr().out
    assert "wong · aaaaaaaaaaaa:24: correct; strategy listed" in out
    written = list((tmp_path / "attempts" / "wong").glob("*"))
    assert {p.suffix for p in written} == {".json", ".md", ".pdf"}

    assert grade_answer.main([str(scan), "--student", "wong", "--paper", "p", "--qid", "24"]) == 0
    assert grade_answer.main([str(scan), "--student", "wong", "--question", "nokey"]) == 1
    assert grade_answer.main([str(tmp_path / "missing.pdf"), "--student", "w", "--question", "aaaaaaaaaaaa:24"]) == 1
