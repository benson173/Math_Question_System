"""Check taxonomy/skills.csv and taxonomy/error_patterns.csv, and summarise them.

    python3 -m scripts.check_taxonomy

Run after editing either file. Exit 1 if anything is wrong.
"""

from __future__ import annotations

from collections import Counter

from app.taxonomy import (ERROR_PATTERNS_CSV, FORMS, SKILLS_CSV, STRANDS,
                          read_error_patterns, read_skills, validate)


def main() -> int:
    skills = read_skills(SKILLS_CSV)
    errors = read_error_patterns(ERROR_PATTERNS_CSV)
    problems = validate(skills, errors)

    print(f"{len(skills)} skills, {len(errors)} error patterns\n")
    by_strand = Counter(s.strand for s in skills)
    for code, name in STRANDS.items():
        print(f"  {name:28} {by_strand.get(code, 0):4}")
    print()
    by_form = Counter(s.form for s in skills)
    print("  " + "   ".join(f"{form} {by_form.get(form, 0):3}" for form in FORMS))
    foundation = Counter(s.foundation for s in skills if s.foundation)
    print(f"  Compulsory Part: {foundation.get('foundation', 0)} foundation, "
          f"{foundation.get('non-foundation', 0)} non-foundation")
    covered = {skill for e in errors for skill in e.skills}
    print(f"  {len(covered)} skills have at least one error pattern")

    if problems:
        print(f"\n{len(problems)} problem(s):")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("\nTaxonomy OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
