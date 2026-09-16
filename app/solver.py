"""The Solver: follow each strategy the Analyzer listed and see if it works.

It is a check on the Analyzer, not a source of answers (spec §5: the Solver
may solve, it may not rate or rewrite). A strategy the Solver cannot carry to
the answer is the Analyzer's problem: it is marked rejected. A Solver answer
that disagrees with the marking scheme is reported, never silently kept.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from app.analyzer import AnalysisResult
from app.paths import PROMPT_SOLVER_V1, project_absolute
from app.rpdice import StrategySolution
from app.schemas import ExtractedQuestion, ExtractionResult, ValidationIssue


SOLVER_BATCH = 8        # questions per call: worked solutions are long


class SolverPayload(BaseModel):
    solutions: list[StrategySolution]


# --- the prompt ---------------------------------------------------------------

def diagram_images(extraction: ExtractionResult, question_ids: list[str]) -> list[tuple[str, bytes]]:
    """(question id, PNG bytes) for every rendered diagram of these questions, in order."""
    out = []
    for image in extraction.diagrams:
        if image.kind != "diagram" or image.source_question_id not in question_ids:
            continue
        path = project_absolute(image.image_path)
        if path.exists():
            out.append((image.source_question_id, path.read_bytes()))
    return out


def figures_block(images: list[tuple[str, bytes]]) -> str:
    if not images:
        return ""
    lines = ["FIGURES (attached images, in this order)"]
    for n, (qid, _) in enumerate(images, 1):
        lines.append(f"image {n}: the diagram of question {qid}")
    return "\n".join(lines)


def pairs_block(extraction: ExtractionResult, analysis: AnalysisResult,
                question_ids: Optional[list[str]] = None) -> str:
    questions = {q.source_question_id: q for q in extraction.document.questions}
    rows = []
    for a in analysis.analyses:
        q = questions.get(a.source_question_id)
        if q is None or (question_ids is not None and a.source_question_id not in question_ids):
            continue
        rows.append({
            "source_question_id": a.source_question_id,
            "question_text": q.question_text,
            "options": list(q.options),
            "reference_answer": q.answer,
            "has_diagram": q.diagram_required,
            "possible_errors": list(a.possible_errors),
            "strategies": [{"strategy_id": s.strategy_id, "strategy_name": s.strategy_name,
                            "steps": list(s.steps)} for s in a.strategies],
        })
    return "PAIRS\n" + json.dumps(rows, ensure_ascii=False, indent=1)


def build_solver_prompt(extraction: ExtractionResult, analysis: AnalysisResult,
                        question_ids: Optional[list[str]] = None,
                        prompt_path: Path = PROMPT_SOLVER_V1,
                        images: Optional[list[tuple[str, bytes]]] = None) -> str:
    head = Path(prompt_path).read_text(encoding="utf-8")
    blocks = [head, figures_block(images or []), pairs_block(extraction, analysis, question_ids)]
    return "\n\n".join(b for b in blocks if b)


# --- comparing answers ------------------------------------------------------

_MC_LETTER = re.compile(r"^\(?([A-Da-d])\)?(?:[\s.:)]|$)")
_LEADING_VAR = re.compile(r"^[a-zA-Z]\s*=\s*")
_NUMBER = re.compile(r"^[-+]?\d+(?:\.\d+)?$")
_FRACTION = re.compile(r"^\(?([-+]?\d+)\)?\s*/\s*\(?(\d+)\)?$")
_UNITS = re.compile(r"(平方單位|立方單位|單位|分|cm[²³23]?|m[²³23]?|km|度|°)+$")


def strip_latex(s: str) -> str:
    """LaTeX as the models write it, down to plain text: \frac{a}{b} -> (a)/(b)."""
    s = re.sub(r"\\[\(\)\[\]]", "", s)                       # \( \) \[ \]
    s = re.sub(r"\\(left|right|,|;|!|quad|displaystyle)", "", s)
    s = re.sub(r"\\sqrt\s*\{([^{}]*)\}", r"sqrt(\1)", s)
    s = re.sub(r"\^\{([^{}]*)\}", r"^\1", s)
    s = re.sub(r"_\{([^{}]*)\}", r"_\1", s)
    frac = re.compile(r"\\(?:d|t)?frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}")
    while frac.search(s):                                       # innermost first
        s = frac.sub(lambda m: f"({m.group(1)})/({m.group(2)})", s)
    s = re.sub(r"\((\w+)\)", r"\1", s)                            # (9)/(2) -> 9/2
    s = s.replace("\\pm", "±").replace("\\times", "*").replace("\\cdot", "*").replace("\\pi", "π")
    s = re.sub(r"\\(?:text|mathrm|mbox)\s*\{([^{}]*)\}", r"\1", s)
    s = re.sub(r"\\[a-zA-Z]+", "", s)                             # any other command
    return s.replace("{", "").replace("}", "")


def normalise_answer(text: Optional[str]) -> Optional[str]:
    """One comparable form: option letter, a number, or lower-cased text."""
    if text is None or not str(text).strip():
        return None
    s = str(text).strip()
    m = _MC_LETTER.match(s)
    if m:
        return m.group(1).upper()
    s = strip_latex(s)
    s = _LEADING_VAR.sub("", s.strip())
    s = s.replace("−", "-").replace("×", "*").replace("，", ",").rstrip(".。 ")
    s = "".join(s.split()).lower().replace("$", "")
    s = _UNITS.sub("", s).rstrip(".。")
    s = re.sub(r"^\((-?\d+(?:\.\d+)?)\)$", r"\1", s)              # (5) -> 5
    m = _FRACTION.match(s)
    if m and int(m.group(2)):
        return _fmt(int(m.group(1)) / int(m.group(2)))
    if _NUMBER.match(s):
        return _fmt(float(s))
    return s


def _fmt(value: float) -> str:
    return f"{value:.6g}"


def answers_match(given: Optional[str], reference: Optional[str]) -> Optional[bool]:
    """True / False, or None when there is nothing to compare against."""
    a, b = normalise_answer(given), normalise_answer(reference)
    if a is None or b is None:
        return None
    if a == b:
        return True
    # "B (1024)" against a bare value, or a value against a bare letter, cannot be judged
    if len(a) == 1 and len(b) != 1 or len(b) == 1 and len(a) != 1:
        inner = re.search(r"\(([^()]+)\)", str(given) + str(reference))
        return normalise_answer(inner.group(1)) == (b if len(a) == 1 else a) if inner else None
    return False


# --- checking what came back ------------------------------------------------

def check_solutions(analysis: AnalysisResult, extraction: ExtractionResult,
                    solutions: list[StrategySolution],
                    diagrams_sent: Optional[set] = None) -> list[ValidationIssue]:
    """Deterministic checks: every strategy solved, answers agree with the scheme.

    A question that needs its diagram, solved without one, is not a failed
    strategy: it is SOLUTION_NEEDS_DIAGRAM, and the strategy stays unverified.
    """
    issues: list[ValidationIssue] = []
    questions = {q.source_question_id: q for q in extraction.document.questions}
    diagrams_sent = diagrams_sent or set()

    def report(code, severity, qid, message):
        issues.append(ValidationIssue(issue_code=code, severity=severity, message=message,
                                      source_question_id=qid))

    got = {(s.source_question_id, s.strategy_id): s for s in solutions}
    for a in analysis.analyses:
        for st in a.strategies:
            solution = got.get((a.source_question_id, st.strategy_id))
            if solution is None:
                report("SOLUTION_MISSING", "medium", a.source_question_id,
                       f"{a.source_question_id}: the Solver returned nothing for strategy "
                       f"{st.strategy_name!r} ({st.strategy_id}).")
                continue
            q: Optional[ExtractedQuestion] = questions.get(a.source_question_id)
            if not solution.reached_answer:
                if q is not None and q.diagram_required and a.source_question_id not in diagrams_sent:
                    report("SOLUTION_NEEDS_DIAGRAM", "medium", a.source_question_id,
                           f"{a.source_question_id}: [{st.strategy_id}] strategy "
                           f"{st.strategy_name!r} needs the diagram, which was not available; "
                           f"render it (RENDER_DIAGRAMS=true) and run critique_rpdice --again.")
                else:
                    report("STRATEGY_DOES_NOT_SOLVE", "high", a.source_question_id,
                           f"{a.source_question_id}: [{st.strategy_id}] strategy "
                           f"{st.strategy_name!r} did not reach an answer: "
                           f"{solution.notes or 'no reason given'}.")
                continue
            verdict = answers_match(solution.final_answer, q.answer if q else None)
            if verdict is False:
                report("ANSWER_MISMATCH", "high", a.source_question_id,
                       f"{a.source_question_id}: strategy {st.strategy_name!r} reached "
                       f"{solution.final_answer!r} but the reference answer is {q.answer!r}.")
    known = {(a.source_question_id, s.strategy_id) for a in analysis.analyses for s in a.strategies}
    for key, solution in got.items():
        if key not in known:
            report("SOLUTION_FOR_UNKNOWN_STRATEGY", "low", key[0],
                   f"{key[0]}: a solution for strategy id {key[1]!r}, which is not in the analysis.")
    # the same strategy answered twice with different results is worth knowing
    by_question: dict[str, set] = {}
    for s in solutions:
        if s.reached_answer and s.final_answer:
            by_question.setdefault(s.source_question_id, set()).add(normalise_answer(s.final_answer))
    for qid, answers in by_question.items():
        if len(answers) > 1:
            report("STRATEGIES_DISAGREE", "high", qid,
                   f"{qid}: the strategies reach different answers: {sorted(a for a in answers if a)}.")
    return issues


# --- running it ---------------------------------------------------------------

class Solver:
    def __init__(self, gemini=None):
        from app.gemini_client import GeminiClient
        self.gemini = gemini or GeminiClient()
        self.usage = {"input_tokens": 0, "output_tokens": 0}
        self.diagrams_sent: set = set()      # question ids whose diagram went with the prompt

    def solve(self, extraction: ExtractionResult, analysis: AnalysisResult) -> list[StrategySolution]:
        ids = [a.source_question_id for a in analysis.analyses]
        solutions: list[StrategySolution] = []
        self.diagrams_sent = set()
        for start in range(0, len(ids), SOLVER_BATCH):
            batch = ids[start:start + SOLVER_BATCH]
            images = diagram_images(extraction, batch)
            prompt = build_solver_prompt(extraction, analysis, batch, images=images)
            if images:
                self.diagrams_sent.update(qid for qid, _ in images)
                payload: SolverPayload = self.gemini.generate_json(
                    prompt, SolverPayload, images=[(data, "image/png") for _, data in images])
            else:
                payload = self.gemini.generate_json(prompt, SolverPayload)
            solutions.extend(payload.solutions)
            usage = getattr(self.gemini, "last_usage", {}) or {}
            for k in self.usage:
                if usage.get(k) is not None:
                    self.usage[k] += usage[k]
        return solutions
