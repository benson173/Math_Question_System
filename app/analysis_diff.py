"""Two Analyzer runs of the same paper, question by question.

The Analyzer is a model at temperature 0, and two runs still disagree on
about a level in ten. This is how that is measured: which letters moved,
which skills came and went, whether the primary strategy changed. Run it
after every prompt change, and on two runs with no change at all to know
the noise floor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.analyzer import AnalysisResult
from app.rpdice import DIMENSIONS, QuestionAnalysis, profile_summary


@dataclass
class QuestionDiff:
    source_question_id: str
    before: Optional[QuestionAnalysis]
    after: Optional[QuestionAnalysis]
    levels: dict[str, tuple[int, int]] = field(default_factory=dict)   # letter -> (old, new)
    skills_added: list[str] = field(default_factory=list)
    skills_removed: list[str] = field(default_factory=list)
    errors_added: list[str] = field(default_factory=list)
    errors_removed: list[str] = field(default_factory=list)
    primary_changed: bool = False
    strategy_count: tuple[int, int] = (0, 0)
    confidence: tuple[float, float] = (0.0, 0.0)

    @property
    def changed(self) -> bool:
        return bool(self.levels or self.skills_added or self.skills_removed or self.primary_changed
                    or self.errors_added or self.errors_removed or self.before is None
                    or self.after is None)


@dataclass
class AnalysisDiff:
    before_run: str
    after_run: str
    questions: list[QuestionDiff]

    @property
    def changed(self) -> list[QuestionDiff]:
        return [q for q in self.questions if q.changed]

    def letter_counts(self) -> dict[str, int]:
        return {d: sum(1 for q in self.questions if d in q.levels) for d in DIMENSIONS}


def diff_analyses(before: AnalysisResult, after: AnalysisResult) -> AnalysisDiff:
    a = {x.source_question_id: x for x in before.analyses}
    b = {x.source_question_id: x for x in after.analyses}
    order = list(a) + [q for q in b if q not in a]
    questions = []
    for qid in order:
        old, new = a.get(qid), b.get(qid)
        d = QuestionDiff(qid, old, new)
        if old is not None and new is not None:
            lo, ln = old.levels(), new.levels()
            d.levels = {k: (lo[k], ln[k]) for k in DIMENSIONS if lo.get(k) != ln.get(k)}
            d.skills_added = sorted(set(new.atomic_skills) - set(old.atomic_skills))
            d.skills_removed = sorted(set(old.atomic_skills) - set(new.atomic_skills))
            d.errors_added = sorted(set(new.possible_errors) - set(old.possible_errors))
            d.errors_removed = sorted(set(old.possible_errors) - set(new.possible_errors))
            po, pn = old.primary(), new.primary()
            d.primary_changed = bool(po and pn) and _same_strategy(po, pn) is False
            d.strategy_count = (len(old.strategies), len(new.strategies))
            d.confidence = (old.confidence, new.confidence)
        questions.append(d)
    return AnalysisDiff(before.run.run_id, after.run.run_id, questions)


def _same_strategy(x, y) -> bool:
    if x.strategy_id and y.strategy_id:
        return x.strategy_id == y.strategy_id
    return x.strategy_name.strip().lower() == y.strategy_name.strip().lower()


def render_diff(diff: AnalysisDiff, taxonomy=None) -> str:
    def name(skill_id):
        if taxonomy is not None and skill_id in taxonomy.skills:
            return taxonomy.skills[skill_id].name_en
        return skill_id

    n = len(diff.questions)
    changed = diff.changed
    level_q = sum(1 for q in changed if q.levels)
    skill_q = sum(1 for q in changed if q.skills_added or q.skills_removed)
    primary_q = sum(1 for q in changed if q.primary_changed)
    letters = diff.letter_counts()
    lines = [f"Runs {diff.before_run} -> {diff.after_run}: {n} questions, "
             f"{len(changed)} changed, {n - len(changed)} identical",
             f"  levels moved in {level_q} questions ({sum(letters.values())} letters of {6 * n}): "
             + "  ".join(f"{d} {letters[d]}" for d in DIMENSIONS),
             f"  skills changed in {skill_q}, primary strategy changed in {primary_q}", ""]
    for q in changed:
        if q.before is None or q.after is None:
            lines.append(f"Q{q.source_question_id}: only in {'after' if q.before is None else 'before'}")
            continue
        head = f"Q{q.source_question_id}: `{profile_summary(q.before.levels())}` -> " \
               f"`{profile_summary(q.after.levels())}`"
        moves = " ".join(f"{d}{o}->{v}" for d, (o, v) in q.levels.items())
        lines.append(head + (f"   {moves}" if moves else ""))
        for s in q.skills_added:
            lines.append(f"    + skill {name(s)}")
        for s in q.skills_removed:
            lines.append(f"    - skill {name(s)}")
        for e in q.errors_added:
            lines.append(f"    + error {e}")
        for e in q.errors_removed:
            lines.append(f"    - error {e}")
        if q.primary_changed:
            lines.append(f"    primary: {q.before.primary().strategy_name!r} -> "
                         f"{q.after.primary().strategy_name!r}")
        if q.strategy_count[0] != q.strategy_count[1]:
            lines.append(f"    strategies: {q.strategy_count[0]} -> {q.strategy_count[1]}")
    return "\n".join(lines)
