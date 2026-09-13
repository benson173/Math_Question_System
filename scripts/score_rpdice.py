"""Compare Analyzer output with the hand-rated golden set.

    python3 -m scripts.score_rpdice                       # every data/analyses/*.json
    python3 -m scripts.score_rpdice data/analyses/x.json
    python3 -m scripts.score_rpdice --check               # only validate the gold file

Prints and writes data/analyses/score-<timestamp>.md. This is the number to
watch when the prompt changes: exact agreement per dimension, and bias.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys

from app.analyzer import load_analysis
from app.paths import ANALYSES_DIR, RPDICE_GOLD_CSV
from app.rpdice import read_gold, render_scorecard, score_against_gold, validate_gold
from app.taxonomy import load_taxonomy


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    taxonomy = load_taxonomy()
    gold = read_gold(RPDICE_GOLD_CSV)
    problems = validate_gold(gold, taxonomy)
    confirmed = sum(1 for g in gold if g.status == "confirmed")
    print(f"Golden set: {len(gold)} questions ({confirmed} confirmed, "
          f"{len(gold) - confirmed} draft)")
    if problems:
        print("Problems in the golden set:")
        for p in problems:
            print(f"  - {p}")
        return 1
    if "--check" in args:
        print("Golden set OK.")
        return 0

    paths = [Path(a) for a in args if not a.startswith("--")] or \
        sorted(p for p in ANALYSES_DIR.glob("*.json"))
    if not paths:
        print(f"No analyses in {ANALYSES_DIR}. Run scripts.analyse_rpdice first.")
        return 0

    analyses = {}
    for path in paths:
        try:
            analyses.update(load_analysis(path).by_key())
        except Exception as exc:
            print(f"skipped {path.name}: {type(exc).__name__}")
    card = score_against_gold(analyses, gold)
    report = render_scorecard(card)
    print(report)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ANALYSES_DIR / f"score-{stamp}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
