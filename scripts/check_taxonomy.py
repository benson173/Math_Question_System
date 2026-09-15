"""Check taxonomy/skills.csv and taxonomy/error_patterns.csv, and summarise them.

    python3 -m scripts.check_taxonomy

Run after editing either file. Exit 1 if anything is wrong.
"""

from __future__ import annotations

from collections import Counter

from app.taxonomy import (ERROR_PATTERNS_CSV, FORMS, GUIDE_OBJECTIVES_CSV, SKILLS_CSV, STRANDS,
                          Taxonomy, read_error_patterns, read_guide_objectives, read_skills,
                          validate)


def main() -> int:
    skills = read_skills(SKILLS_CSV)
    errors = read_error_patterns(ERROR_PATTERNS_CSV)
    objectives = read_guide_objectives(GUIDE_OBJECTIVES_CSV)
    problems = validate(skills, errors, objectives)

    print(f"{len(skills)} skills, {len(errors)} error patterns\n")
    by_strand = Counter(s.strand for s in skills)
    for code, name in STRANDS.items():
        print(f"  {name:28} {by_strand.get(code, 0):4}")
    print()
    by_form = Counter(s.form for s in skills)
    print("  " + "   ".join(f"{form} {by_form.get(form, 0):3}" for form in FORMS))
    foundation = Counter(s.foundation for s in skills if s.foundation)
    print(f"  KS3 + Compulsory Part: {foundation.get('foundation', 0)} foundation, "
          f"{foundation.get('non-foundation', 0)} non-foundation, "
          f"{foundation.get('enrichment', 0)} enrichment")
    covered = {skill for e in errors for skill in e.skills}
    print(f"  {len(covered)} skills have at least one error pattern")

    taxonomy = Taxonomy({s.skill_id: s for s in skills}, {e.error_id: e for e in errors},
                        {o.ref: o for o in objectives})
    ext = [s.skill_id for s in skills if "ext" in s.guide_ref]
    assessed = [o for o in objectives if o.status != "enrichment"]
    uncovered = taxonomy.uncovered_objectives()
    print(f"\n  Guide: {len(objectives)} objectives ({len(assessed)} assessed), "
          f"{len(assessed) - len(uncovered)} covered by at least one skill")
    if uncovered:
        print("  objectives with no skill:")
        for o in uncovered:
            print(f"    {o.ref:9} {o.text[:80]}")
    print(f"  {len(ext)} skills outside the Guide (guide_ref = ext): {', '.join(ext)}")

    if problems:
        print(f"\n{len(problems)} problem(s):")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("\nTaxonomy OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
