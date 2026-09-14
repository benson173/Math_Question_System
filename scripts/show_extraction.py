"""Read back a saved extraction, without re-running Gemini.

    python -m scripts.show_extraction                 # newest JSON
    python -m scripts.show_extraction 17              # only question 17 and its parts
    python -m scripts.show_extraction --file x.json 17

Use it to check what was actually captured: the terminal output during
ingestion is a summary, this is the stored data.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.paths import EXTRACTED_DIR


def newest_extraction() -> Path:
    files = sorted(EXTRACTED_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime)
    if not files:
        raise SystemExit(f"No extraction JSON in {EXTRACTED_DIR}")
    return files[-1]


def matches(question_id: str, wanted: str) -> bool:
    """'17' matches 17, 17(a), 17(b)(i); '17(a)' matches only that part."""
    return question_id == wanted or question_id.startswith(f"{wanted}(")


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    path = newest_extraction()
    if "--file" in args:
        index = args.index("--file")
        path = Path(args[index + 1])
        del args[index:index + 2]
    wanted = args[0] if args else None

    data = json.loads(path.read_text(encoding="utf-8"))
    document, source, run = data["document"], data.get("source"), data.get("run")

    print(f"File   : {path}")
    print(f"PDF    : {document['file_name']}  ({document['page_count']} pages)")
    level = document.get("level")
    print(f"Level  : {level} (from {document.get('level_source')})" if level
          else "Level  : unknown")
    if source:
        print(f"SHA256 : {source['sha256']}")
    if run:
        print(f"Run    : {run['run_id']}  {run['extracted_at']}  {run['model']}")
    print(f"Questions: {len(document['questions'])}")

    questions = document["questions"]
    if wanted:
        questions = [q for q in questions if matches(q["source_question_id"], wanted)]
        if not questions:
            print(f"\nNo question matching {wanted!r}.")
            return 1

    for q in questions:
        print("\n" + "=" * 70)
        labels = []
        if q.get("marks") is not None:
            labels.append(f"{q['marks']} marks")
        elif q.get("group_marks") is not None:
            labels.append(f"{q['group_marks']} marks for "
                          f"{q.get('group_marks_scope') or 'the group'}")
        if q.get("diagram_required"):
            labels.append("diagram")
        if q.get("depends_on"):
            labels.append("depends on " + ", ".join(q["depends_on"]))
        suffix = f"  [{', '.join(labels)}]" if labels else ""
        print(f"{q['source_question_id']}  "
              f"p{q['page_start']}-{q['page_end']}{suffix}  "
              f"({len(q['question_text'])} chars)")
        print("-" * 70)
        print(q["question_text"])
        if q.get("answer"):
            print(f"\nANSWER: {q['answer']}")
        if q.get("worked_solution"):
            print(f"\nSOLUTION: {q['worked_solution']}")
        for note in q.get("extraction_notes", []):
            print(f"\nNOTE: {note}")

    for label, key in (("DIAGRAMS", "diagrams"), ("TABLES", "tables")):
        assets = data.get(key, [])
        if not assets:
            continue
        print("\n" + "=" * 70)
        print(f"{label}: {len(assets)}")
        for asset in assets:
            kind = "cropped" if asset["cropped"] else "full page"
            print(f"  {asset['source_question_id']:10} p{asset['page']}  "
                  f"{asset['width']}x{asset['height']}  {kind}")
            print(f"             {asset['image_path']}")

    issues = data.get("issues", [])
    print("\n" + "=" * 70)
    print(f"ISSUES: {len(issues)}")
    for issue in issues:
        where = f" ({issue['source_question_id']})" if issue.get("source_question_id") else ""
        print(f"  {issue['severity']:8} {issue['issue_code']}{where}")
        print(f"           {issue['message']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
