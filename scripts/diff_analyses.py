"""Compare two Analyzer runs of the same paper.

    python3 -m scripts.diff_analyses a.json b.json          # any two analysis JSONs
    python3 -m scripts.diff_analyses 2526_2nd_S4MATH2       # the two newest runs of that paper
                                                              # (data/analyses/history/<stem>-<sha>/)

Prints which levels, skills, errors and primary strategies moved. Two runs
with the same prompt and model show the Analyzer's noise floor; a prompt
change is judged against that.
"""

from __future__ import annotations

from pathlib import Path
import sys

from app.analysis_diff import diff_analyses, render_diff
from app.analyzer import load_analysis
from app.paths import ANALYSES_DIR
from app.taxonomy import load_taxonomy


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) == 2:
        paths = [Path(args[0]), Path(args[1])]
    elif len(args) == 1:
        paths = newest_two(args[0])
        if paths is None:
            print(f"Need two runs of a paper matching {args[0]!r} under {ANALYSES_DIR / 'history'}.")
            return 1
    else:
        print(__doc__)
        return 2
    before, after = (load_analysis(p) for p in paths)
    if before.sha256 != after.sha256:
        print(f"Warning: different papers ({before.file_name} / {after.file_name}); "
              f"questions are matched by id only.")
    if before.run.analysed_at > after.run.analysed_at:
        before, after = after, before
    print(render_diff(diff_analyses(before, after), load_taxonomy()))
    return 0


def newest_two(stem: str):
    folders = [f for f in (ANALYSES_DIR / "history").glob("*") if f.is_dir() and stem in f.name]
    runs = sorted((p for f in folders for p in f.glob("*.json")), key=lambda p: p.stat().st_mtime)
    return runs[-2:] if len(runs) >= 2 else None


if __name__ == "__main__":
    raise SystemExit(main())
