"""Read one student's handwritten answer to one question.

    python3 -m scripts.grade_answer inbox/answers/wong.pdf --question b584940bfebb:24 --student wong
    python3 -m scripts.grade_answer scan.jpg --paper 2526_2nd_S4MATH2 --qid 24 --student s001

The question is named by its question_key (<sha12>:<id>, printed in every
extraction and analysis report) or by paper stem plus question id. The
paper's extraction and analysis must exist under data/. Writes
data/attempts/<student>/<key>-<run>.json and .md, and pushes to Supabase
(students, attempts) when .env is set.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys

from app.analyzer import load_analysis
from app.extraction_io import load_extraction
from app.grader import ATTEMPTS_DIR, Grader, attempt_path, export_attempt, render_attempt_markdown
from app.paths import ANALYSES_DIR, EXTRACTED_DIR
from scripts.analyse_rpdice import _client


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("scan", help="PDF or image of the student's page")
    parser.add_argument("--student", required=True, help="student id (any stable string)")
    parser.add_argument("--question", help="question_key, e.g. b584940bfebb:24")
    parser.add_argument("--paper", help="paper stem, e.g. 2526_2nd_S4MATH2 (with --qid)")
    parser.add_argument("--qid", help="source_question_id, e.g. 24 or 17(a)")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    scan = Path(args.scan)
    if not scan.exists():
        print(f"No such file: {scan}")
        return 1
    located = locate(args.question, args.paper, args.qid)
    if located is None:
        return 1
    extraction_path, analysis_path, qid = located

    extraction = load_extraction(extraction_path)
    analysis = load_analysis(analysis_path)
    grader = Grader()
    attempt = grader.grade(scan, args.student, extraction, analysis, qid)

    out = export_attempt(attempt, attempt_path(attempt))
    kept = out.with_name(out.stem + scan.suffix.lower())
    shutil.copyfile(scan, kept)                     # the page stays next to its reading
    out.with_suffix(".md").write_text(render_attempt_markdown(attempt, grader.taxonomy, kept.name),
                                      encoding="utf-8")
    verdict = {True: "correct", False: "wrong", None: "not marked"}[attempt.is_correct]
    print(f"{attempt.student_id} · {attempt.question_key}: {verdict}; strategy {attempt.strategy_match}"
          + (f" {attempt.strategy_id}" if attempt.strategy_id else "")
          + f"; {len(attempt.skills_evidenced)} skills shown, {len(attempt.skills_not_evidenced)} not; "
          f"{len(attempt.slips)} slips, {len(attempt.misconceptions)} misconceptions")
    if attempt.needs_human:
        print("  needs a person: " + "; ".join(attempt.review_reasons))
    print(f"  {out}\n  {out.with_suffix('.md')}")
    client = _client()
    if client is not None:
        from app.attempt_store import push_attempt
        try:
            push_attempt(client, attempt)
            print("  Supabase: attempt saved")
        except Exception as exc:
            print(f"  Warning: not saved to Supabase ({type(exc).__name__}: {exc})")
    return 0


def locate(question_key: str | None, paper: str | None, qid: str | None):
    """(extraction path, analysis path, qid) for a question_key or a paper + qid."""
    if question_key:
        if ":" not in question_key:
            print(f"{question_key!r} is not a question_key (<sha12>:<question id>)")
            return None
        sha12, qid = question_key.split(":", 1)
        matches = sorted(EXTRACTED_DIR.glob(f"*-{sha12}.json"))
    elif paper and qid:
        matches = sorted(p for p in EXTRACTED_DIR.glob("*.json") if p.stem.startswith(paper))
    else:
        print("Give --question <key>, or --paper <stem> with --qid <id>.")
        return None
    if not matches:
        print(f"No extraction under {EXTRACTED_DIR} for that paper.")
        return None
    extraction_path = matches[0]
    analysis_path = ANALYSES_DIR / extraction_path.name
    if not analysis_path.exists():
        print(f"No analysis at {analysis_path}; run python3 -m scripts.analyse_rpdice first.")
        return None
    return extraction_path, analysis_path, qid


if __name__ == "__main__":
    raise SystemExit(main())
