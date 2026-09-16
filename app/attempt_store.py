"""Rows for the students and attempts tables.

An attempt hangs off question_key (never a questions row id) and, when the
working follows a listed strategy, off that strategy's strategy_id inside
question_analyses.strategies. The Student Model reads attempts; nothing
here interprets them.
"""

from __future__ import annotations

from typing import Any

from app.grader import GradedAttempt


TABLE_STUDENTS = "students"
TABLE_ATTEMPTS = "attempts"


def attempt_row(attempt: GradedAttempt) -> dict[str, Any]:
    return {
        "student_id": attempt.student_id,
        "question_key": attempt.question_key,
        "source_question_id": attempt.source_question_id,
        "paper_file_name": attempt.paper_file_name,
        "scan_file_name": attempt.scan_file_name,
        "scan_sha256": attempt.scan_sha256,
        "grader_run_id": attempt.run.run_id,
        "grader_version": attempt.run.grader_version,
        "model": attempt.run.model,
        "answer_given": attempt.reading.option_chosen or attempt.reading.final_answer,
        "is_correct": attempt.is_correct,
        "strategy_id": attempt.strategy_id,
        "strategy_match": attempt.strategy_match,
        "skills_evidenced": list(attempt.skills_evidenced),
        "skills_not_evidenced": list(attempt.skills_not_evidenced),
        "error_ids": list(attempt.error_ids),
        "slips": list(attempt.slips),
        "misconceptions": list(attempt.misconceptions),
        "transcription": list(attempt.reading.transcription),
        "confidence": attempt.reading.confidence,
        "needs_human": attempt.needs_human,
        "review_reasons": list(attempt.review_reasons),
        "attempted_at": attempt.run.graded_at,
    }


def push_attempt(client, attempt: GradedAttempt) -> int:
    """The student row if new, then the attempt. Returns rows written."""
    client.table(TABLE_STUDENTS).upsert({"student_id": attempt.student_id},
                                        on_conflict="student_id").execute()
    client.table(TABLE_ATTEMPTS).insert(attempt_row(attempt)).execute()
    return 1
