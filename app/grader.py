"""The Grader: one student's handwritten page for one question.

A vision model reads the page and reports what is written, which listed
strategy the working follows, which skills the working shows and what went
wrong. Code decides correctness against the reference answer, names the
skills the primary strategy expects but the page does not show, and flags
what a person must look at. This is where a strategy_id first points back
from a student to the question analysis.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Optional
import uuid

from pydantic import BaseModel, Field

from app.analyzer import AnalysisResult
from app.config import load_settings
from app.gemini_client import prompt_sha256
from app.paths import DATA_DIR, PROMPT_GRADER_V1
from app.question_key import question_key
from app.schemas import ExtractedQuestion, ExtractionResult
from app.solver import answers_match, normalise_answer
from app.taxonomy import Taxonomy


ATTEMPTS_DIR = DATA_DIR / "attempts"
GRADER_VERSION = "grader_v1"
MIME = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg", ".webp": "image/webp"}
LOW_CONFIDENCE = 0.6


class ErrorObservation(BaseModel):
    error_id: Optional[str] = None
    kind: str = "slip"                 # slip | misconception
    description: str = ""


class GraderPayload(BaseModel):
    """What the vision model returns."""

    transcription: list[str] = Field(default_factory=list)
    final_answer: Optional[str] = None
    option_chosen: Optional[str] = None
    strategy_id_matched: Optional[str] = None
    strategy_description: str = ""
    skills_evidenced: list[str] = Field(default_factory=list)
    errors_observed: list[ErrorObservation] = Field(default_factory=list)
    unclear: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class GraderRun(BaseModel):
    run_id: str
    graded_at: str
    grader_version: str
    model: str
    prompt_sha256: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None


class GradedAttempt(BaseModel):
    """One attempt, as stored: the model's reading plus the pipeline's verdicts."""

    student_id: str
    question_key: str
    source_question_id: str
    paper_file_name: str
    scan_file_name: str
    scan_sha256: str
    run: GraderRun
    reading: GraderPayload
    is_correct: Optional[bool] = None          # None when there is no reference answer
    reference_answer: Optional[str] = None
    reference_source: Optional[str] = None     # marking_scheme | solver | None
    strategy_id: Optional[str] = None          # a listed strategy the working follows
    strategy_match: str = "none"               # listed | new | none
    skills_evidenced: list[str] = Field(default_factory=list)
    skills_not_evidenced: list[str] = Field(default_factory=list)   # expected by the primary strategy
    error_ids: list[str] = Field(default_factory=list)
    slips: list[str] = Field(default_factory=list)
    misconceptions: list[str] = Field(default_factory=list)
    needs_human: bool = False
    review_reasons: list[str] = Field(default_factory=list)


# --- the prompt ---------------------------------------------------------------

def find_question(extraction: ExtractionResult, qid: str) -> ExtractedQuestion:
    for q in extraction.document.questions:
        if q.source_question_id == qid:
            return q
    raise KeyError(f"question {qid!r} is not in {extraction.document.file_name}")


def question_skills(analysis, taxonomy: Taxonomy) -> list[str]:
    """The skills the page could show: those listed for the question, plus what they rest on."""
    listed = list(analysis.atomic_skills) + [s for st in analysis.strategies for s in st.skills]
    out: list[str] = list(dict.fromkeys(listed))
    for skill_id in list(out):
        if skill_id in taxonomy.skills:
            for pre in taxonomy.prerequisites_closure(skill_id):
                if pre not in out:
                    out.append(pre)
    return out


def build_grader_prompt(question: ExtractedQuestion, analysis, taxonomy: Taxonomy,
                        prompt_path: Path = PROMPT_GRADER_V1) -> str:
    head = Path(prompt_path).read_text(encoding="utf-8")
    context = {
        "question_text": question.question_text,
        "options": list(question.options),
        "strategies": [{"strategy_id": s.strategy_id, "strategy_name": s.strategy_name,
                        "steps": list(s.steps), "skills": list(s.skills)} for s in analysis.strategies],
    }
    skills = ["SKILLS (skill_id | name)"]
    for skill_id in question_skills(analysis, taxonomy):
        if skill_id in taxonomy.skills:
            skills.append(f"{skill_id} | {taxonomy.skills[skill_id].name_en}")
    errors = ["ERRORS (error_id | name)"]
    seen = set()
    for error_id in list(analysis.possible_errors):
        if error_id in taxonomy.errors and error_id not in seen:
            seen.add(error_id)
            errors.append(f"{error_id} | {taxonomy.errors[error_id].name_en}")
    for skill_id in question_skills(analysis, taxonomy):
        for pattern in taxonomy.errors_for_skill(skill_id):
            if pattern.error_id not in seen and not pattern.is_general:
                seen.add(pattern.error_id)
                errors.append(f"{pattern.error_id} | {pattern.name_en}")
    return "\n\n".join([head, "QUESTION\n" + json.dumps(context, ensure_ascii=False, indent=1),
                        "\n".join(skills), "\n".join(errors)])


# --- deciding -------------------------------------------------------------------

def reference_for(question: ExtractedQuestion, analysis, analysis_result: Optional[AnalysisResult]):
    """(answer, source): the marking scheme when there is one, else the Solver's
    answer along a confirmed strategy of this question, else nothing."""
    if question.answer:
        return question.answer, "marking_scheme"
    if analysis_result is not None:
        confirmed = {s.strategy_id for s in analysis.strategies if s.status == "confirmed"}
        for solution in analysis_result.solutions:
            if (solution.source_question_id == analysis.source_question_id
                    and solution.strategy_id in confirmed and solution.reached_answer
                    and solution.final_answer):
                return solution.final_answer, "solver"
    return None, None


def decide(reading: GraderPayload, question: ExtractedQuestion, analysis,
           taxonomy: Taxonomy, reference: Optional[str] = None,
           reference_source: Optional[str] = None) -> dict:
    """Everything the pipeline decides from the reading; pure, testable.

    `reference` defaults to the question's own answer; the Grader passes the
    Solver's confirmed answer when there is no marking scheme.
    """
    if reference is None and reference_source is None:
        reference, reference_source = (question.answer, "marking_scheme") if question.answer else (None, None)
    given = reading.option_chosen or reading.final_answer
    is_correct = answers_match(given, reference)
    if is_correct is None and reference and reading.option_chosen and question.options:
        # a letter against a value: look the option up
        letters = "ABCDEFGH"
        idx = letters.find(reading.option_chosen.strip().upper()[:1])
        if 0 <= idx < len(question.options):
            is_correct = answers_match(question.options[idx], reference)
    if is_correct is None and reference and reading.final_answer and reading.option_chosen:
        is_correct = answers_match(reading.final_answer, reference)

    listed = {s.strategy_id: s for s in analysis.strategies if s.strategy_id}
    if reading.strategy_id_matched in listed:
        strategy_id, match = reading.strategy_id_matched, "listed"
    elif reading.transcription and reading.strategy_description:
        strategy_id, match = None, "new"
    else:
        strategy_id, match = None, "none"

    known = set(taxonomy.skills)
    evidenced = [s for s in dict.fromkeys(reading.skills_evidenced) if s in known]
    expected_from = listed.get(strategy_id) if strategy_id else analysis.primary()
    expected = list(expected_from.skills) if expected_from else list(analysis.atomic_skills)
    not_evidenced = [s for s in expected if s not in evidenced]

    error_ids, slips, misconceptions = [], [], []
    for obs in reading.errors_observed:
        text = obs.description or obs.error_id or ""
        if obs.error_id and obs.error_id in taxonomy.errors and obs.error_id not in error_ids:
            error_ids.append(obs.error_id)
            text = f"{obs.error_id}: {obs.description}" if obs.description else obs.error_id
        (misconceptions if obs.kind == "misconception" else slips).append(text)

    reasons = []
    if reading.unclear:
        reasons.append(f"unreadable: {'; '.join(reading.unclear)}")
    if reading.confidence < LOW_CONFIDENCE:
        reasons.append(f"low confidence {reading.confidence:.2f}")
    if match == "new":
        reasons.append("the working follows no listed strategy")
    if is_correct is None:
        reasons.append("no reference answer to mark against")
    if is_correct and misconceptions:
        reasons.append("correct answer but a misconception was reported")
    return dict(is_correct=is_correct, reference_answer=reference, reference_source=reference_source,
                strategy_id=strategy_id,
                strategy_match=match, skills_evidenced=evidenced, skills_not_evidenced=not_evidenced,
                error_ids=error_ids, slips=slips, misconceptions=misconceptions,
                needs_human=bool(reasons), review_reasons=reasons)


# --- running it ---------------------------------------------------------------

class Grader:
    def __init__(self, gemini=None, taxonomy: Optional[Taxonomy] = None):
        from app.gemini_client import GeminiClient
        from app.taxonomy import load_taxonomy
        self.settings = load_settings()
        self.gemini = gemini or GeminiClient()
        self.taxonomy = taxonomy or load_taxonomy()

    def grade(self, scan: Path, student_id: str, extraction: ExtractionResult,
              analysis_result: AnalysisResult, qid: str) -> GradedAttempt:
        scan = Path(scan)
        mime = MIME.get(scan.suffix.lower())
        if mime is None:
            raise ValueError(f"{scan.name}: not a PDF or image ({', '.join(MIME)})")
        data = scan.read_bytes()
        question = find_question(extraction, qid)
        analysis = next((a for a in analysis_result.analyses if a.source_question_id == qid), None)
        if analysis is None:
            raise KeyError(f"question {qid!r} has no analysis in run {analysis_result.run.run_id}")
        prompt = build_grader_prompt(question, analysis, self.taxonomy)
        reading: GraderPayload = self.gemini.generate_json(prompt, GraderPayload, images=[(data, mime)])
        usage = getattr(self.gemini, "last_usage", {}) or {}
        reference, source = reference_for(question, analysis, analysis_result)
        verdict = decide(reading, question, analysis, self.taxonomy, reference, source)
        return GradedAttempt(
            student_id=student_id,
            question_key=question_key(extraction.source.sha256, qid),
            source_question_id=qid,
            paper_file_name=extraction.document.file_name,
            scan_file_name=scan.name,
            scan_sha256=hashlib.sha256(data).hexdigest(),
            run=GraderRun(run_id=uuid.uuid4().hex[:12],
                          graded_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                          grader_version=GRADER_VERSION,
                          model=getattr(self.gemini, "model", None) or self.settings.gemini_extractor_model,
                          prompt_sha256=prompt_sha256(PROMPT_GRADER_V1),
                          input_tokens=usage.get("input_tokens"),
                          output_tokens=usage.get("output_tokens")),
            reading=reading,
            **verdict,
        )


# --- saving -------------------------------------------------------------------

def attempt_path(attempt: GradedAttempt) -> Path:
    safe_key = attempt.question_key.replace(":", "_").replace("(", "").replace(")", "")
    return ATTEMPTS_DIR / attempt.student_id / f"{safe_key}-{attempt.run.run_id}.json"


def export_attempt(attempt: GradedAttempt, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(attempt.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def render_attempt_markdown(attempt: GradedAttempt, taxonomy: Taxonomy, scan_relpath: str = "") -> str:
    verdict = {True: "correct", False: "wrong", None: "not marked (no reference answer)"}[attempt.is_correct]
    lines = [f"# Attempt — {attempt.student_id} · {attempt.question_key}", "",
             f"Paper {attempt.paper_file_name} · question {attempt.source_question_id} · scan "
             f"`{attempt.scan_file_name}` · grader run `{attempt.run.run_id}` · {attempt.run.model}", ""]
    if scan_relpath:
        lines += [f"![scan]({scan_relpath})", ""]
    answered = attempt.reading.option_chosen or attempt.reading.final_answer
    if attempt.reading.option_chosen and attempt.reading.final_answer:
        answered = f"{attempt.reading.option_chosen} ({attempt.reading.final_answer})"
    lines += [f"**Verdict: {verdict}** — answered {answered!r}"
              + (f", reference {attempt.reference_answer!r} ({attempt.reference_source})"
                 if attempt.reference_answer else ""), ""]
    if attempt.needs_human:
        lines += ["> Needs a person: " + "; ".join(attempt.review_reasons), ""]
    lines += ["## Transcription", ""] + [f"    {line}" for line in attempt.reading.transcription] + [""]
    lines += ["## Route", "",
              f"- strategy: {attempt.strategy_match}"
              + (f" `{attempt.strategy_id}`" if attempt.strategy_id else ""),
              f"- {attempt.reading.strategy_description}" if attempt.reading.strategy_description else "", ""]

    def name(skill_id):
        return taxonomy.skills[skill_id].name_en if skill_id in taxonomy.skills else skill_id
    lines += ["## Skills", ""]
    lines += [f"- ✓ {name(s)} (`{s}`)" for s in attempt.skills_evidenced]
    lines += [f"- ✗ not shown: {name(s)} (`{s}`)" for s in attempt.skills_not_evidenced]
    lines.append("")
    if attempt.slips or attempt.misconceptions:
        lines += ["## Errors", ""]
        lines += [f"- slip: {s}" for s in attempt.slips]
        lines += [f"- misconception: {m}" for m in attempt.misconceptions]
        lines.append("")
    if attempt.reading.unclear:
        lines += ["## Unclear", ""] + [f"- {u}" for u in attempt.reading.unclear] + [""]
    lines.append(f"Reading confidence {attempt.reading.confidence:.2f}")
    return "\n".join(line for line in lines if line is not None)
