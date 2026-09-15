"""Rows for the question_analyses table, and how to write them.

An analysis hangs off question_key, never off the questions row id, so a
re-extraction of the paper does not orphan it. Every Analyzer run is kept;
the newest non-failing one per question is is_current.
"""

from __future__ import annotations

from typing import Any

from app.analyzer import AnalysisResult
from app.question_key import question_key
from app.rpdice import drivers_of


TABLE_ANALYSES = "question_analyses"


def analysis_rows(result: AnalysisResult) -> list[dict[str, Any]]:
    by_question = {}
    for issue in result.issues:
        by_question.setdefault(issue.source_question_id, []).append(issue.model_dump())
    rows = []
    for a in result.analyses:
        primary = a.primary()
        levels = primary.rpdice.levels() if primary else {}
        rows.append({
            "question_key": question_key(result.sha256, a.source_question_id),
            "source_sha256": result.sha256,
            "source_question_id": a.source_question_id,
            "analysis_run_id": result.run.run_id,
            "analyzer_version": result.run.analyzer_version,
            "prompt_sha256": result.run.prompt_sha256,
            "model": result.run.model,
            "level": result.level,
            "module": result.module,
            "skill_family": a.skill_family,
            "atomic_skills": list(a.atomic_skills),
            "method_cues": list(a.method_cues),
            "strategies": [s.model_dump() for s in a.strategies],
            "rpdice": levels,
            "difficulty_drivers": drivers_of(levels),
            "possible_errors": list(a.possible_errors),
            "proposed_skills": list(a.proposed_skills),
            "proposed_errors": list(a.proposed_errors),
            "confidence": a.confidence,
            "issues": by_question.get(a.source_question_id, []),
            "is_current": True,
        })
    return rows


def push_analysis(client, result: AnalysisResult) -> int:
    rows = analysis_rows(result)
    if not rows:
        return 0
    client.table(TABLE_ANALYSES).insert(rows).execute()
    for row in rows:
        (client.table(TABLE_ANALYSES).update({"is_current": False})
         .eq("question_key", row["question_key"])
         .neq("analysis_run_id", result.run.run_id)
         .eq("is_current", True).execute())
    return len(rows)
