"""Run the Solver and Critic over saved analyses that have not been reviewed.

    python3 -m scripts.critique_rpdice                        # every analysis in data/analyses
    python3 -m scripts.critique_rpdice data/analyses/x.json   # just this paper
    python3 -m scripts.critique_rpdice --again                # also the ones already critiqued

Each analysis is paired with its extraction (same file name under
data/extracted). The analysis JSON and Markdown are rewritten in place with
the solutions, the Critic's issues and each strategy's status, and the run is
pushed again to Supabase when .env is set.
"""

from __future__ import annotations

from pathlib import Path
import sys

from app.analyzer import export_analysis_json, load_analysis, render_analysis_markdown
from app.critic import Critic, critique
from app.extraction_io import load_extraction
from app.paths import ANALYSES_DIR, EXTRACTED_DIR
from app.solver import Solver
from app.taxonomy import load_taxonomy
from scripts.analyse_rpdice import _client, _status_line


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    again = "--again" in args
    args = [a for a in args if a != "--again"]
    paths = [Path(a) for a in args] or sorted(ANALYSES_DIR.glob("*.json"))
    if not paths:
        print(f"No analysis JSON in {ANALYSES_DIR}. Run python3 -m scripts.analyse_rpdice first.")
        return 0

    todo, failed = [], 0
    for path in paths:
        try:
            analysis = load_analysis(path)
        except Exception:
            print(f"skipped {path.name}")
            continue
        if analysis.critic is not None and not again:
            print(f"{path.name}: already critiqued (run {analysis.critic.run_id}); use --again")
            continue
        extraction_path = EXTRACTED_DIR / path.name
        if not extraction_path.exists():
            print(f"{path.name}: no extraction at {extraction_path}")
            failed += 1
            continue
        todo.append((path, analysis, extraction_path))
    if not todo:
        return 1 if failed else 0

    taxonomy = load_taxonomy()
    solver, critic, client = Solver(), Critic(), _client()      # Gemini only when there is work
    for path, analysis, extraction_path in todo:
        print("=" * 70)
        print(f"{analysis.file_name}: {len(analysis.analyses)} questions")
        try:
            critique(load_extraction(extraction_path), analysis, solver, critic)
        except Exception as exc:
            failed += 1
            print(f"  FAILED {type(exc).__name__}: {exc}")
            continue
        export_analysis_json(analysis, path)
        path.with_suffix(".md").write_text(render_analysis_markdown(analysis, taxonomy),
                                           encoding="utf-8")
        high = [i for i in analysis.critic_issues if i.severity == "high"]
        print(f"  {len(analysis.solutions)} strategies solved, {len(analysis.critic_issues)} "
              f"critic issues ({len(high)} high), {_status_line(analysis)}")
        if client is not None:
            from app.analysis_store import push_analysis
            try:
                print(f"  Supabase: {push_analysis(client, analysis)} rows")
            except Exception as exc:
                print(f"  Warning: not saved to Supabase ({type(exc).__name__}: {exc})")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
