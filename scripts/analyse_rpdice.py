"""Run the RPDICE Analyzer over saved extractions.

    python3 -m scripts.analyse_rpdice                          # every JSON in data/extracted
    python3 -m scripts.analyse_rpdice data/extracted/x.json    # just this paper

Writes data/analyses/<paper>-<hash>.json and .md, and a history copy per run.
Pushes to Supabase (question_analyses) when .env is set. Then compare with the
golden set: python3 -m scripts.score_rpdice
"""

from __future__ import annotations

from pathlib import Path
import sys

from app.analyzer import (RpdiceAnalyzer, analysis_history_path, analysis_output_path,
                          export_analysis_json, render_analysis_markdown)
from app.config import load_settings
from app.extraction_io import load_extractions
from app.paths import EXTRACTED_DIR
from app.supabase_store import StoreError, connect, key_warning


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    paths = [Path(a) for a in args] or sorted(EXTRACTED_DIR.glob("*.json"))
    if not paths:
        print(f"No extraction JSON in {EXTRACTED_DIR}. Ingest a paper first.")
        return 0

    analyzer = RpdiceAnalyzer()
    client = _client()
    failed = 0
    for path, result in load_extractions(paths, on_skip=lambda p, e: print(f"skipped {p.name}")):
        print("=" * 70)
        print(f"{result.document.file_name}: {len(result.document.questions)} questions")
        try:
            analysis = analyzer.analyse(result)
        except Exception as exc:
            failed += 1
            print(f"  FAILED {type(exc).__name__}: {exc}")
            continue
        out = export_analysis_json(analysis, analysis_output_path(analysis))
        export_analysis_json(analysis, analysis_history_path(analysis))
        md = out.with_suffix(".md")
        md.write_text(render_analysis_markdown(analysis, analyzer.taxonomy), encoding="utf-8")
        blocking = [i for i in analysis.issues if i.severity in ("critical", "high")]
        print(f"  {len(analysis.analyses)} analysed, {len(analysis.issues)} issues "
              f"({len(blocking)} high or critical)")
        print(f"  {out}\n  {md}")
        if client is not None:
            from app.analysis_store import push_analysis
            try:
                print(f"  Supabase: {push_analysis(client, analysis)} rows")
            except Exception as exc:
                print(f"  Warning: not saved to Supabase ({type(exc).__name__}: {exc})")
    return 1 if failed else 0


def _client():
    settings = load_settings()
    url, key = settings.supabase_url, settings.supabase_secret_key
    if not url or not key or url.startswith("put_") or key.startswith("put_"):
        print("Storage: JSON files only - Supabase not configured")
        return None
    warning = key_warning(key)
    if warning:
        print(f"Warning: {warning}")
    try:
        return connect(url, key)
    except StoreError as exc:
        print(f"Warning: {exc}")
        return None


if __name__ == "__main__":
    raise SystemExit(main())
