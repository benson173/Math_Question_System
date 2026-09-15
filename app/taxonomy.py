"""The controlled vocabularies the later layers speak in.

Two CSV files under taxonomy/ are the source of truth:

    skills.csv           one row per atomic skill, HKDSE Compulsory Part + KS3
    error_patterns.csv   one row per error a question can expose (RPDICE "E")

They are curated by hand. The Analyzer chooses from them and may not invent
entries; the Student Model counts mastery by skill_id; student errors are
tagged by error_id and compared with what the Analyzer said a question would
expose. A free-text skill name would split one skill into several spellings
and make all of that meaningless, so every id here is checked, not trusted.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Iterable, Optional

from app.paths import PROJECT_ROOT


TAXONOMY_DIR = PROJECT_ROOT / "taxonomy"
SKILLS_CSV = TAXONOMY_DIR / "skills.csv"
ERROR_PATTERNS_CSV = TAXONOMY_DIR / "error_patterns.csv"

# The Compulsory Part (and Key Stage 3 below it) is organised in strands; the
# two Extended Part modules are each a strand of their own.
COMPULSORY_STRANDS = ("na", "ms", "dh", "fl")
MODULE_STRANDS = {"m1": "M1", "m2": "M2"}
STRANDS = {
    "na": "Number and Algebra",
    "ms": "Measures, Shape and Space",
    "dh": "Data Handling",
    "fl": "Further Learning Unit",
    "m1": "Module 1 (Calculus and Statistics)",
    "m2": "Module 2 (Algebra and Calculus)",
}
FORMS = ("F1", "F2", "F3", "F4", "F5", "F6")
FOUNDATION = {"": None, "F": "foundation", "N": "non-foundation"}

_SKILL_ID = re.compile(r"^(na|ms|dh|fl|m1|m2)\.[a-z0-9-]+\.[a-z0-9-]+$")
_ERROR_ID = re.compile(r"^err\.[a-z0-9-]+\.[a-z0-9-]+$")


@dataclass(frozen=True)
class Skill:
    skill_id: str
    strand: str
    unit: str
    name_en: str
    name_zh: str
    form: str
    foundation: Optional[str]          # "foundation" | "non-foundation" | None (KS3)
    prerequisites: tuple[str, ...] = ()


@dataclass(frozen=True)
class ErrorPattern:
    error_id: str
    name_en: str
    name_zh: str
    skills: tuple[str, ...]
    description: str = ""


@dataclass
class Taxonomy:
    skills: dict[str, Skill] = field(default_factory=dict)
    errors: dict[str, ErrorPattern] = field(default_factory=dict)

    def skills_for_form(self, form: str) -> list[Skill]:
        return [s for s in self.skills.values() if s.form == form]

    def skills_in_unit(self, unit: str) -> list[Skill]:
        return [s for s in self.skills.values() if s.unit == unit]

    def skills_for_module(self, module: Optional[str]) -> list[Skill]:
        """Every skill a paper of this module can draw on.

        M1 and M2 are built on the Compulsory Part, so an Extended Part paper
        gets its own strand plus everything compulsory; a compulsory paper
        never gets M1 or M2 skills.
        """
        wanted = set(COMPULSORY_STRANDS)
        for strand, name in MODULE_STRANDS.items():
            if module == name:
                wanted.add(strand)
        return [s for s in self.skills.values() if s.strand in wanted]

    def errors_for_skill(self, skill_id: str) -> list[ErrorPattern]:
        return [e for e in self.errors.values() if skill_id in e.skills]

    def prerequisites_closure(self, skill_id: str) -> list[str]:
        """Every skill this one rests on, nearest first, without repeats."""
        seen: list[str] = []
        frontier = list(self.skills[skill_id].prerequisites)
        while frontier:
            current = frontier.pop(0)
            if current in seen or current not in self.skills:
                continue
            seen.append(current)
            frontier.extend(self.skills[current].prerequisites)
        return seen


# --- reading ------------------------------------------------------------------

def _rows(path: Path) -> list[dict[str, str]]:
    """CSV rows as dicts, comment lines (#) and blank lines skipped."""
    with Path(path).open(encoding="utf-8", newline="") as handle:
        lines = [line for line in handle if line.strip() and not line.lstrip().startswith("#")]
    return list(csv.DictReader(lines))


def _split(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in (value or "").split(";") if part.strip())


def read_skills(path: Path = SKILLS_CSV) -> list[Skill]:
    skills = []
    for row in _rows(path):
        skills.append(Skill(
            skill_id=row["skill_id"].strip(),
            strand=row["strand"].strip(),
            unit=row["unit"].strip(),
            name_en=row["name_en"].strip(),
            name_zh=row["name_zh"].strip(),
            form=row["form"].strip(),
            foundation=FOUNDATION.get(row.get("foundation", "").strip(), "?"),
            prerequisites=_split(row.get("prerequisites", "")),
        ))
    return skills


def read_error_patterns(path: Path = ERROR_PATTERNS_CSV) -> list[ErrorPattern]:
    return [ErrorPattern(
        error_id=row["error_id"].strip(),
        name_en=row["name_en"].strip(),
        name_zh=row["name_zh"].strip(),
        skills=_split(row.get("skills", "")),
        description=(row.get("description") or "").strip(),
    ) for row in _rows(path)]


# --- checking -----------------------------------------------------------------

def validate(skills: Iterable[Skill], errors: Iterable[ErrorPattern]) -> list[str]:
    """Every way the two files can be wrong, as plain sentences."""
    problems: list[str] = []
    skills, errors = list(skills), list(errors)
    ids = [s.skill_id for s in skills]
    known = set(ids)

    for skill_id in ids:
        if ids.count(skill_id) > 1:
            problems.append(f"skill {skill_id} appears more than once")
    for s in skills:
        if not _SKILL_ID.match(s.skill_id):
            problems.append(f"skill id {s.skill_id!r} is not <strand>.<unit>.<slug>")
        elif s.skill_id.split(".")[0] != s.strand:
            problems.append(f"skill {s.skill_id} says strand {s.strand!r} but its id says "
                            f"{s.skill_id.split('.')[0]!r}")
        if s.strand not in STRANDS:
            problems.append(f"skill {s.skill_id} has unknown strand {s.strand!r}")
        if s.form not in FORMS:
            problems.append(f"skill {s.skill_id} has form {s.form!r}, not F1-F6")
        if s.foundation == "?":
            problems.append(f"skill {s.skill_id} has a foundation flag that is not F, N or blank")
        compulsory = s.strand in COMPULSORY_STRANDS
        if compulsory and s.form in ("F4", "F5", "F6") and s.foundation is None:
            problems.append(f"skill {s.skill_id} is Compulsory Part ({s.form}) but has no "
                            f"foundation flag")
        if compulsory and s.form in ("F1", "F2", "F3") and s.foundation is not None:
            problems.append(f"skill {s.skill_id} is KS3 ({s.form}) but has a foundation flag")
        if not compulsory and s.foundation is not None:
            problems.append(f"skill {s.skill_id} is {STRANDS[s.strand]}, where the "
                            f"Foundation / Non-Foundation split does not apply")
        if not s.name_en or not s.name_zh:
            problems.append(f"skill {s.skill_id} is missing an English or Chinese name")
        for pre in s.prerequisites:
            if pre not in known:
                problems.append(f"skill {s.skill_id} needs {pre}, which does not exist")
            elif pre == s.skill_id:
                problems.append(f"skill {s.skill_id} lists itself as a prerequisite")

    problems.extend(_cycles({s.skill_id: s.prerequisites for s in skills if s.skill_id in known}))

    error_ids = [e.error_id for e in errors]
    for error_id in error_ids:
        if error_ids.count(error_id) > 1:
            problems.append(f"error {error_id} appears more than once")
    for e in errors:
        if not _ERROR_ID.match(e.error_id):
            problems.append(f"error id {e.error_id!r} is not err.<topic>.<slug>")
        if not e.skills:
            problems.append(f"error {e.error_id} belongs to no skill")
        for skill_id in e.skills:
            if skill_id not in known:
                problems.append(f"error {e.error_id} refers to {skill_id}, which does not exist")
        if not e.name_en or not e.name_zh:
            problems.append(f"error {e.error_id} is missing an English or Chinese name")

    return sorted(set(problems))


def _cycles(graph: dict[str, tuple[str, ...]]) -> list[str]:
    """A prerequisite chain that comes back to its start."""
    problems = []
    state: dict[str, int] = {}          # 1 = visiting, 2 = done

    def visit(node: str, path: list[str]) -> None:
        if state.get(node) == 2:
            return
        if state.get(node) == 1:
            loop = path[path.index(node):] + [node]
            problems.append("prerequisite cycle: " + " -> ".join(loop))
            return
        state[node] = 1
        for pre in graph.get(node, ()):
            if pre in graph:
                visit(pre, path + [node])
        state[node] = 2

    for start in graph:
        visit(start, [])
    return problems


def load_taxonomy(skills_path: Path = SKILLS_CSV,
                  errors_path: Path = ERROR_PATTERNS_CSV) -> Taxonomy:
    """Both files, checked. Raises with every problem if there are any."""
    skills = read_skills(skills_path)
    errors = read_error_patterns(errors_path)
    problems = validate(skills, errors)
    if problems:
        raise ValueError("The taxonomy has problems:\n  " + "\n  ".join(problems))
    return Taxonomy({s.skill_id: s for s in skills}, {e.error_id: e for e in errors})
