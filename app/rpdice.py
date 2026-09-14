"""The RPDICE standard: what each level of each dimension means, the shape an
analysis takes, and the checks that decide whether an analysis is usable.

RPDICE measures the structural cognitive demand of a question or a solution
strategy. It never measures student ability or empirical difficulty; those
come later, from student data. Everything here is derivable from the question
text, its options, and the strategy being described - nothing else.

Levels are 0-3 per dimension. They are ordinal ("this demand is stronger"),
not a difficulty score, and they are never added up: a question is described
by its vector and by which dimensions drive it.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas import Severity, ValidationIssue


DIMENSIONS = ("R", "P", "D", "I", "C", "E")
DIMENSION_NAMES = {
    "R": "Recognition", "P": "Procedure", "D": "Decision",
    "I": "Integration", "C": "Cognitive Depth", "E": "Error Exposure",
}
MAX_LEVEL = 3
DRIVER_THRESHOLD = 2          # a dimension at this level or above drives the question

# The standard. One sentence per level, written so that two raters looking at
# the same question and strategy land on the same number. The prompt is
# generated from this table, so the model and the human read the same words.
LEVELS: dict[str, dict[int, str]] = {
    "R": {
        0: "Nothing to recognise: the object to work on is stated outright (solve 2x + 3 = 7).",
        1: "One standard form to spot, cued by the notation itself (9a² − 25 is a² − b²; a "
           "right-angled triangle with two sides given).",
        2: "A hidden structure or a re-reading is required before any method applies: treat "
           "(2x + 1) as one unit, see 225x² as (15x)², find similar triangles in an "
           "overlapping figure, see that a condition on roots is a discriminant condition.",
        3: "Recognition is the crux and nothing cues it: an equation quadratic in log₂ x, a "
           "geometric fact hidden inside a coordinate problem, a game as an infinite "
           "geometric series.",
    },
    "P": {
        0: "No procedure beyond reading a value or stating a fact.",
        1: "One standard routine, short: apply one identity, one formula, one substitution.",
        2: "Several routines chained, or one routine made awkward by fractions, surds, "
           "parameters, completing the square, or long division.",
        3: "A long chain where slips accumulate: multi-stage algebra with parameters, several "
           "triangles in one 3-D figure, or a routine with case handling. Repeating one "
           "routine many times does not raise P above 2.",
    },
    "D": {
        0: "The method is stated in the question (利用二次公式, 利用配方法, Hence) or only one "
           "method exists.",
        1: "The obvious standard approach for this topic works; recognise and apply.",
        2: "A genuine choice between two or more viable methods, or the order matters "
           "(simplify first or substitute first), or a representation must be chosen "
           "(algebra or graph).",
        3: "A strategy has to be devised: no standard method fits directly, so sub-goals, an "
           "auxiliary line or variable, or which earlier result to reuse must be decided.",
    },
    "I": {
        0: "One atomic skill.",
        1: "Several skills from the same unit or skill family (factorise, then solve).",
        2: "Skills from two different units must be linked (trigonometry with coordinate "
           "geometry; percentages with logarithms).",
        3: "Three or more units, or the link needs a translation between representations "
           "(a geometric fact becomes an algebraic condition becomes an inequality). "
           "Repeating one technique ten times is not integration.",
    },
    "C": {
        0: "One step, direct.",
        1: "Sequential steps, each fixed by the previous, forward only.",
        2: "One of: reasoning backwards from a result to a condition, a case split, checking "
           "or rejecting candidate solutions, or an 'explain' that needs a computed "
           "comparison.",
        3: "A proof, a generalisation, or a claim to evaluate that needs an argument or a "
           "counter-example built; or a later part whose use of an earlier result is "
           "non-obvious. C is not the number of steps: a short question can be a 3.",
    },
    "E": {
        0: "No common error pattern applies.",
        1: "One typical slip (a sign, an arithmetic step) that a student would notice.",
        2: "A known misconception from the error catalogue is directly triggered (flip the "
           "inequality, an extraneous root, the wrong base), or two or more slip points.",
        3: "Several misconception traps, or an error that yields a plausible-looking answer "
           "with no way to notice it (a quadrant sign, dependent events treated as "
           "independent). E is what the question would expose, not what students will do.",
    },
}

# Words that state the method: when one is in the question text, D cannot be
# above 1 (the prompt says so, and the validator checks it).
METHOD_CUE_PATTERNS = (
    r"利用[^，。]{0,12}(公式|定理|配方法|因式分解|代入|圖像|對數)",
    r"用[^，。]{0,6}(配方法|二次公式|因式分解法|圖解法)",
    r"以[^，。]{0,6}(配方法|二次公式|因式分解法|圖解法)",
    r"\b(use|using|by|apply|applying)\s+(the\s+)?(quadratic formula|completing the square|"
    r"factori[sz]ation|factor theorem|remainder theorem|sine rule|cosine rule|"
    r"difference of two squares|a graphical method|substitution|elimination)",
    r"\bhence\b", r"由此", r"利用\s*\([a-z]+\)",
)
_CUE = re.compile("|".join(f"(?:{p})" for p in METHOD_CUE_PATTERNS), re.IGNORECASE)
MAX_D_WITH_CUE = 1


def method_cues_in(text: str) -> list[str]:
    """The method-stating phrases printed in a question, verbatim."""
    return [m.group(0) for m in _CUE.finditer(text or "")]


# --- what an analysis looks like --------------------------------------------

class Dimension(BaseModel):
    level: int
    evidence: list[str] = Field(default_factory=list)


class RpdiceProfile(BaseModel):
    R: Dimension
    P: Dimension
    D: Dimension
    I: Dimension
    C: Dimension
    E: Dimension

    def levels(self) -> dict[str, int]:
        return {d: getattr(self, d).level for d in DIMENSIONS}


class Strategy(BaseModel):
    strategy_name: str
    steps: list[str]
    skills: list[str] = Field(default_factory=list)      # skill_ids
    rpdice: RpdiceProfile
    is_primary: bool = False


class QuestionAnalysis(BaseModel):
    """Structural analysis of one question. empirical_difficulty stays null."""

    source_question_id: str
    skill_family: str
    atomic_skills: list[str] = Field(default_factory=list)      # skill_ids
    method_cues: list[str] = Field(default_factory=list)        # verbatim from the text
    representation_features: list[str] = Field(default_factory=list)
    strategies: list[Strategy]
    possible_errors: list[str] = Field(default_factory=list)    # error_ids
    difficulty_drivers: list[str] = Field(default_factory=list) # dimension letters
    structural_depth_notes: list[str] = Field(default_factory=list)
    proposed_skills: list[str] = Field(default_factory=list)    # free text, for review
    proposed_errors: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    empirical_difficulty: Optional[float] = None

    def primary(self) -> Optional[Strategy]:
        flagged = [s for s in self.strategies if s.is_primary]
        return flagged[0] if flagged else (self.strategies[0] if self.strategies else None)

    def levels(self) -> dict[str, int]:
        primary = self.primary()
        return primary.rpdice.levels() if primary else {}


class AnalysisPayload(BaseModel):
    """What the Analyzer model is asked to return."""

    analyses: list[QuestionAnalysis]


def drivers_of(levels: dict[str, int]) -> list[str]:
    return [d for d in DIMENSIONS if levels.get(d, 0) >= DRIVER_THRESHOLD]


# --- checking an analysis ---------------------------------------------------

def validate_analysis(analysis: QuestionAnalysis, question_text: str,
                      taxonomy) -> list[ValidationIssue]:
    """Everything that makes an analysis unusable or suspect.

    `taxonomy` is an app.taxonomy.Taxonomy. Unknown skills are only an error
    if they are not also declared as proposals: proposing is allowed, silently
    inventing is not.
    """
    issues: list[ValidationIssue] = []
    qid = analysis.source_question_id

    def report(code: str, severity: Severity, message: str) -> None:
        issues.append(ValidationIssue(issue_code=code, severity=severity,
                                      message=message, source_question_id=qid))

    if not analysis.strategies:
        report("NO_STRATEGY", "critical", f"{qid}: no solution strategy given.")
        return issues

    primaries = [s for s in analysis.strategies if s.is_primary]
    if len(primaries) != 1:
        report("PRIMARY_STRATEGY_COUNT", "medium",
               f"{qid}: {len(primaries)} strategies marked primary; exactly one is expected.")

    for strategy in analysis.strategies:
        for letter in DIMENSIONS:
            dim: Dimension = getattr(strategy.rpdice, letter)
            if not 0 <= dim.level <= MAX_LEVEL:
                report("RPDICE_LEVEL_OUT_OF_RANGE", "high",
                       f"{qid}: {letter} = {dim.level} in {strategy.strategy_name!r}; "
                       f"levels are 0-{MAX_LEVEL}.")
            elif dim.level > 0 and not dim.evidence:
                report("RPDICE_EVIDENCE_MISSING", "medium",
                       f"{qid}: {letter} = {dim.level} with no evidence in "
                       f"{strategy.strategy_name!r}.")
        if not strategy.steps:
            report("STRATEGY_WITHOUT_STEPS", "medium",
                   f"{qid}: strategy {strategy.strategy_name!r} has no steps.")

    known_skills = set(taxonomy.skills)
    all_skills = list(analysis.atomic_skills) + [s for st in analysis.strategies for s in st.skills]
    for skill in all_skills:
        if skill not in known_skills:
            report("SKILL_UNKNOWN", "high",
                   f"{qid}: skill {skill!r} is not in taxonomy/skills.csv. Put a new skill in "
                   f"proposed_skills, never in atomic_skills.")
    if not analysis.atomic_skills:
        report("NO_SKILLS", "high", f"{qid}: no atomic_skills.")

    listed = set(analysis.atomic_skills)
    for error in analysis.possible_errors:
        pattern = taxonomy.errors.get(error)
        if pattern is None:
            report("ERROR_UNKNOWN", "high",
                   f"{qid}: error {error!r} is not in taxonomy/error_patterns.csv. New errors "
                   f"go in proposed_errors.")
        elif listed and not (set(pattern.skills) & listed):
            report("ERROR_NOT_OF_SKILL", "low",
                   f"{qid}: error {error} belongs to {', '.join(pattern.skills)}, none of "
                   f"which is in atomic_skills.")

    for cue in analysis.method_cues:
        if cue and cue not in (question_text or ""):
            report("METHOD_CUE_NOT_IN_TEXT", "medium",
                   f"{qid}: method cue {cue!r} does not appear in the question text. Cues "
                   f"are copied, not paraphrased.")
    printed_cues = method_cues_in(question_text)
    primary = analysis.primary()
    if printed_cues and primary and primary.rpdice.D.level > MAX_D_WITH_CUE:
        report("DECISION_IGNORES_CUE", "medium",
               f"{qid}: the question states the method ({printed_cues[0]!r}) but D = "
               f"{primary.rpdice.D.level}; with a cue D is at most {MAX_D_WITH_CUE}.")

    if primary:
        expected = drivers_of(primary.rpdice.levels())
        if sorted(analysis.difficulty_drivers) != sorted(expected):
            report("DRIVERS_MISMATCH", "low",
                   f"{qid}: difficulty_drivers {analysis.difficulty_drivers} but the levels "
                   f"say {expected}. Drivers are the dimensions at {DRIVER_THRESHOLD} or above.")
        units = {taxonomy.skills[s].unit for s in analysis.atomic_skills if s in known_skills}
        i_level = primary.rpdice.I.level
        if i_level == 0 and len(analysis.atomic_skills) > 1:
            report("INTEGRATION_INCONSISTENT", "low",
                   f"{qid}: I = 0 but {len(analysis.atomic_skills)} skills are listed.")
        elif i_level >= 2 and len(units) < 2:
            report("INTEGRATION_INCONSISTENT", "low",
                   f"{qid}: I = {i_level} but every listed skill is in one unit "
                   f"({', '.join(units) or 'none'}).")

    if analysis.empirical_difficulty is not None:
        report("EMPIRICAL_NOT_NULL", "high",
               f"{qid}: empirical_difficulty must be null; it comes from student data, never "
               f"from the Analyzer.")
    if not 0.0 <= analysis.confidence <= 1.0:
        report("CONFIDENCE_OUT_OF_RANGE", "medium",
               f"{qid}: confidence {analysis.confidence} is not in 0-1.")
    return issues


# --- the golden set ---------------------------------------------------------

@dataclass(frozen=True)
class GoldRating:
    question_key: str
    paper: str
    source_question_id: str
    skills: tuple[str, ...]
    levels: dict[str, int]
    errors: tuple[str, ...]
    rater: str
    status: str                  # draft | confirmed
    notes: str = ""


def read_gold(path: Path) -> list[GoldRating]:
    with Path(path).open(encoding="utf-8", newline="") as handle:
        lines = [l for l in handle if l.strip() and not l.lstrip().startswith("#")]
    ratings = []
    for row in csv.DictReader(lines):
        ratings.append(GoldRating(
            question_key=row["question_key"].strip(),
            paper=row["paper"].strip(),
            source_question_id=row["source_question_id"].strip(),
            skills=tuple(s.strip() for s in row["skills"].split(";") if s.strip()),
            levels={d: int(row[d]) for d in DIMENSIONS},
            errors=tuple(e.strip() for e in (row.get("errors") or "").split(";") if e.strip()),
            rater=row.get("rater", "").strip(),
            status=row.get("status", "draft").strip() or "draft",
            notes=(row.get("notes") or "").strip(),
        ))
    return ratings


def validate_gold(ratings: list[GoldRating], taxonomy) -> list[str]:
    problems = []
    keys = [r.question_key for r in ratings]
    for key in keys:
        if keys.count(key) > 1:
            problems.append(f"{key} is rated more than once")
    for r in ratings:
        for d, level in r.levels.items():
            if not 0 <= level <= MAX_LEVEL:
                problems.append(f"{r.question_key}: {d} = {level}, not 0-{MAX_LEVEL}")
        for s in r.skills:
            if s not in taxonomy.skills:
                problems.append(f"{r.question_key}: skill {s} does not exist")
        for e in r.errors:
            if e not in taxonomy.errors:
                problems.append(f"{r.question_key}: error {e} does not exist")
        if r.status not in ("draft", "confirmed"):
            problems.append(f"{r.question_key}: status {r.status!r} is not draft or confirmed")
        if not r.skills:
            problems.append(f"{r.question_key}: no skills")
    return sorted(set(problems))


# --- scoring an Analyzer run against gold -----------------------------------

@dataclass
class DimensionScore:
    n: int = 0
    exact: int = 0
    within_one: int = 0
    abs_diff: int = 0
    bias: int = 0                 # sum of (analysis − gold): positive = analyzer rates higher

    @property
    def exact_rate(self) -> float:
        return self.exact / self.n if self.n else 0.0

    @property
    def within_one_rate(self) -> float:
        return self.within_one / self.n if self.n else 0.0

    @property
    def mean_abs(self) -> float:
        return self.abs_diff / self.n if self.n else 0.0

    @property
    def mean_bias(self) -> float:
        return self.bias / self.n if self.n else 0.0


@dataclass
class Scorecard:
    compared: int = 0
    missing: list[str] = field(default_factory=list)      # gold keys with no analysis
    dimensions: dict[str, DimensionScore] = field(
        default_factory=lambda: {d: DimensionScore() for d in DIMENSIONS})
    skill_overlap: list[float] = field(default_factory=list)   # Jaccard per question
    error_overlap: list[float] = field(default_factory=list)
    worst: list[tuple[str, int, dict[str, int], dict[str, int]]] = field(default_factory=list)

    @property
    def mean_skill_overlap(self) -> float:
        return sum(self.skill_overlap) / len(self.skill_overlap) if self.skill_overlap else 0.0

    @property
    def mean_error_overlap(self) -> float:
        return sum(self.error_overlap) / len(self.error_overlap) if self.error_overlap else 0.0


def _jaccard(a, b) -> float:
    a, b = set(a), set(b)
    return len(a & b) / len(a | b) if (a | b) else 1.0


def score_against_gold(analyses: dict[str, QuestionAnalysis],
                       gold: list[GoldRating]) -> Scorecard:
    """`analyses` is keyed by question_key."""
    card = Scorecard()
    for rating in gold:
        analysis = analyses.get(rating.question_key)
        if analysis is None:
            card.missing.append(rating.question_key)
            continue
        levels = analysis.levels()
        card.compared += 1
        total_diff = 0
        for d in DIMENSIONS:
            score = card.dimensions[d]
            got, want = levels.get(d, 0), rating.levels[d]
            diff = got - want
            score.n += 1
            score.exact += diff == 0
            score.within_one += abs(diff) <= 1
            score.abs_diff += abs(diff)
            score.bias += diff
            total_diff += abs(diff)
        card.skill_overlap.append(_jaccard(analysis.atomic_skills, rating.skills))
        card.error_overlap.append(_jaccard(analysis.possible_errors, rating.errors))
        card.worst.append((rating.question_key, total_diff, levels, rating.levels))
    card.worst.sort(key=lambda item: -item[1])
    return card


def render_scorecard(card: Scorecard, top: int = 10) -> str:
    lines = ["# RPDICE agreement with the golden set", "",
             f"Compared {card.compared} questions"
             + (f"; {len(card.missing)} gold questions had no analysis" if card.missing else ""),
             "", "| Dimension | exact | within 1 | mean |diff| | bias |", "|---|---|---|---|---|"]
    for d in DIMENSIONS:
        s = card.dimensions[d]
        lines.append(f"| {d} {DIMENSION_NAMES[d]} | {s.exact_rate:.0%} | {s.within_one_rate:.0%} "
                     f"| {s.mean_abs:.2f} | {s.mean_bias:+.2f} |")
    lines += ["", f"Skill overlap (Jaccard): {card.mean_skill_overlap:.0%}",
              f"Error overlap (Jaccard): {card.mean_error_overlap:.0%}", ""]
    if card.worst:
        lines += ["## Largest disagreements", "",
                  "| question | total |diff| | analyzer RPDICE | gold RPDICE |", "|---|---|---|---|"]
        for key, diff, got, want in card.worst[:top]:
            fmt = lambda lv: "".join(str(lv.get(d, 0)) for d in DIMENSIONS)
            lines.append(f"| {key} | {diff} | {fmt(got)} | {fmt(want)} |")
        lines.append("")
    if card.missing:
        lines += ["## Not analysed", ""] + [f"- {k}" for k in card.missing] + [""]
    return "\n".join(lines)


def rubric_text() -> str:
    """The standard as the model reads it - generated from LEVELS, never retyped."""
    out = []
    for d in DIMENSIONS:
        out.append(f"{d} = {DIMENSION_NAMES[d]}")
        for level in range(MAX_LEVEL + 1):
            out.append(f"  {level}: {LEVELS[d][level]}")
        out.append("")
    return "\n".join(out).rstrip()


def profile_summary(levels: dict[str, int]) -> str:
    """R1 P2 D0 I1 C2 E2 - the compact form used in reports."""
    return " ".join(f"{d}{levels.get(d, 0)}" for d in DIMENSIONS)
