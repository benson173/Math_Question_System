"""The Critic: an independent reader who only finds fault.

It sees the question, the Analyzer's output and the Solver's attempts, and
returns issues in the validator's format. It never rewrites the analysis
(spec §5). Its findings, with the Solver's, decide each strategy's status:
confirmed when the strategy reached the right answer and nothing high was
raised against it, rejected when it did not solve, proposed otherwise.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Optional
import uuid

from pydantic import BaseModel, Field

from app.analyzer import AnalysisResult
from app.config import load_settings
from app.gemini_client import prompt_sha256
from app.paths import PROMPT_CRITIC_V1, PROMPT_SOLVER_V1
from app.rpdice import CriticRun, StrategySolution, rubric_text
from app.schemas import ExtractionResult, ValidationIssue
from app.solver import Solver, check_solutions


CRITIC_VERSION = "critic_v1"
CRITIC_CODES = (
    "STRATEGY_DOES_NOT_SOLVE", "STRATEGY_STEPS_WRONG", "STRATEGY_MISSING", "PRIMARY_NOT_TYPICAL",
    "LEVEL_OVERRATED", "LEVEL_UNDERRATED", "EVIDENCE_NOT_IN_QUESTION", "SKILL_MISSING",
    "SKILL_IRRELEVANT", "ERROR_NOT_TRIGGERED", "ERROR_MISSING", "ANSWER_MISMATCH",
)
SEVERITIES = ("low", "medium", "high")
CRITIC_BATCH = 10


class CriticIssue(BaseModel):
    source_question_id: str
    strategy_id: Optional[str] = None
    issue_code: str
    severity: str = "medium"
    message: str


class CriticPayload(BaseModel):
    issues: list[CriticIssue] = Field(default_factory=list)


# --- the prompt ---------------------------------------------------------------

def review_block(extraction: ExtractionResult, analysis: AnalysisResult,
                 solutions: list[StrategySolution],
                 question_ids: Optional[list[str]] = None) -> str:
    questions = {q.source_question_id: q for q in extraction.document.questions}
    solved: dict[str, list] = {}
    for s in solutions:
        solved.setdefault(s.source_question_id, []).append(s.model_dump())
    rows = []
    for a in analysis.analyses:
        q = questions.get(a.source_question_id)
        if q is None or (question_ids is not None and a.source_question_id not in question_ids):
            continue
        dumped = a.model_dump()
        dumped.pop("empirical_difficulty", None)      # never shown: it is not the Critic's to judge
        rows.append({
            "source_question_id": a.source_question_id,
            "question_text": q.question_text,
            "options": list(q.options),
            "reference_answer": q.answer,
            "level": analysis.level,
            "analysis": dumped,
            "solver": solved.get(a.source_question_id, []),
        })
    return "REVIEW\n" + json.dumps(rows, ensure_ascii=False, indent=1)


def build_critic_prompt(extraction: ExtractionResult, analysis: AnalysisResult,
                        solutions: list[StrategySolution],
                        question_ids: Optional[list[str]] = None,
                        prompt_path: Path = PROMPT_CRITIC_V1) -> str:
    head = Path(prompt_path).read_text(encoding="utf-8").replace("{RUBRIC}", rubric_text())
    return "\n\n".join([head, review_block(extraction, analysis, solutions, question_ids)])


# --- normalising what came back -------------------------------------------------

def normalise_issues(raw: list[CriticIssue], analysis: AnalysisResult) -> list[ValidationIssue]:
    """Critic output as validator issues: known codes, known questions, sane severity."""
    known_q = {a.source_question_id: a for a in analysis.analyses}
    out: list[ValidationIssue] = []
    for issue in raw:
        if issue.source_question_id not in known_q:
            continue
        code = issue.issue_code.strip().upper()
        if code not in CRITIC_CODES:
            code = "CRITIC_OTHER"
        severity = issue.severity.strip().lower()
        if severity not in SEVERITIES:
            severity = "medium"
        message = issue.message.strip()
        if issue.strategy_id and not message.startswith(issue.strategy_id):
            message = f"[{issue.strategy_id}] {message}"
        if not message.startswith(issue.source_question_id):
            message = f"{issue.source_question_id}: {message}"
        out.append(ValidationIssue(issue_code=code, severity=severity, message=message,
                                   source_question_id=issue.source_question_id))
    return out


def apply_status(analysis: AnalysisResult, solutions: list[StrategySolution],
                 issues: list[ValidationIssue]) -> dict[str, int]:
    """confirmed / rejected / proposed for every strategy, from the evidence."""
    solved = {(s.source_question_id, s.strategy_id): s for s in solutions}
    high_against: set = set()
    for i in issues:
        if i.severity == "high":
            for a in analysis.analyses:
                if a.source_question_id != i.source_question_id:
                    continue
                for st in a.strategies:
                    if st.strategy_id and f"[{st.strategy_id}]" in i.message:
                        high_against.add((a.source_question_id, st.strategy_id))
                    elif st.strategy_id and st.strategy_id in i.message:
                        high_against.add((a.source_question_id, st.strategy_id))
    counts = {"confirmed": 0, "rejected": 0, "proposed": 0}
    for a in analysis.analyses:
        for st in a.strategies:
            key = (a.source_question_id, st.strategy_id)
            solution = solved.get(key)
            if solution is None:
                st.status = "proposed"
            elif not solution.reached_answer:
                st.status = "rejected"
            elif key in high_against:
                st.status = "proposed"
            else:
                st.status = "confirmed"
            counts[st.status] += 1
    return counts


# --- running it ---------------------------------------------------------------

class Critic:
    def __init__(self, gemini=None):
        from app.gemini_client import GeminiClient
        self.settings = load_settings()
        self.gemini = gemini or GeminiClient(model=self.settings.gemini_critic_model)
        self.usage = {"input_tokens": 0, "output_tokens": 0}

    def critique(self, extraction: ExtractionResult, analysis: AnalysisResult,
                 solutions: list[StrategySolution]) -> list[ValidationIssue]:
        ids = [a.source_question_id for a in analysis.analyses]
        raw: list[CriticIssue] = []
        for start in range(0, len(ids), CRITIC_BATCH):
            batch = ids[start:start + CRITIC_BATCH]
            prompt = build_critic_prompt(extraction, analysis, solutions, batch)
            payload: CriticPayload = self.gemini.generate_json(prompt, CriticPayload)
            raw.extend(payload.issues)
            usage = getattr(self.gemini, "last_usage", {}) or {}
            for k in self.usage:
                if usage.get(k) is not None:
                    self.usage[k] += usage[k]
        return normalise_issues(raw, analysis)


def critique(extraction: ExtractionResult, analysis: AnalysisResult,
             solver: Optional[Solver] = None, critic: Optional[Critic] = None) -> AnalysisResult:
    """Solver, deterministic checks, Critic, statuses: the analysis, reviewed."""
    solver = solver or Solver()
    critic = critic or Critic()
    solutions = solver.solve(extraction, analysis)
    issues = check_solutions(analysis, extraction, solutions)
    issues += critic.critique(extraction, analysis, solutions)
    apply_status(analysis, solutions, issues)
    analysis.solutions = solutions
    analysis.critic_issues = issues
    analysis.critic = CriticRun(
        run_id=uuid.uuid4().hex[:12],
        critiqued_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        model=getattr(critic.gemini, "model", None) or critic.settings.gemini_critic_model,
        solver_prompt_sha256=prompt_sha256(PROMPT_SOLVER_V1),
        critic_prompt_sha256=prompt_sha256(PROMPT_CRITIC_V1),
        input_tokens=solver.usage["input_tokens"] + critic.usage["input_tokens"],
        output_tokens=solver.usage["output_tokens"] + critic.usage["output_tokens"],
    )
    return analysis
