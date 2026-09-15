"""The controlled vocabularies the later layers speak in.

Three CSV files under taxonomy/ are the source of truth:

    skills.csv           one row per atomic skill, KS3 + Compulsory Part + M1 + M2
    error_patterns.csv   one row per error a question can expose (RPDICE "E")
    guide_objectives.csv the Learning Objectives of the EDB C&A Guide (2017) and
                         the KS3 Supplement, as extracted from the two PDFs

Every skill names the Guide objective(s) it comes from (guide_ref), and the
Foundation / Non-foundation / Enrichment flag is taken from there. Skills and
errors are curated by hand. The Analyzer chooses from them and may not invent
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
GUIDE_OBJECTIVES_CSV = TAXONOMY_DIR / "guide_objectives.csv"

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
FOUNDATION = {"": None, "F": "foundation", "N": "non-foundation", "E": "enrichment"}

# guide_ref: Guide objectives separated by ";" ("CP-1.4", "KS3-11.3", "M1-6.1",
# "M2-9.6", a Further Learning Unit as "CP-19"), "KS2" for primary-school
# knowledge the Guide assumes, or "ext" for a skill outside every Guide
# objective (kept because papers still ask it; flagged so it can be excluded).
GUIDE_PARTS = ("KS3", "CP", "M1", "M2")
_GUIDE_REF = re.compile(r"^(KS3|CP|M1|M2)-\d+(\.\d+)?$")

_SKILL_ID = re.compile(r"^(na|ms|dh|fl|m1|m2)\.[a-z0-9-]+\.[a-z0-9-]+$")
_ERROR_ID = re.compile(r"^err\.[a-z0-9-]+\.[a-z0-9-]+$")

# An error's skills column may also hold "*" (any skill: rounding too early,
# a sign slip) or "<strand>.*" (any skill of that strand: assuming a right
# angle from the diagram is a fault of geometry in general, not of one unit).
_WILDCARD = re.compile(r"^(\*|(na|ms|dh|fl|m1|m2)\.\*)$")


def is_wildcard(entry: str) -> bool:
    return bool(_WILDCARD.match(entry))


def skill_matches(entry: str, skill_id: str) -> bool:
    """Does a skills-column entry (an id or a wildcard) cover this skill?"""
    if entry == "*":
        return True
    if entry.endswith(".*"):
        return skill_id.startswith(entry[:-1])
    return entry == skill_id


@dataclass(frozen=True)
class Skill:
    skill_id: str
    strand: str
    unit: str
    name_en: str
    name_zh: str
    form: str
    foundation: Optional[str]          # foundation | non-foundation | enrichment | None
    prerequisites: tuple[str, ...] = ()
    guide_ref: tuple[str, ...] = ()    # see GUIDE_PARTS

    @property
    def in_guide(self) -> bool:
        return any(_GUIDE_REF.match(r) for r in self.guide_ref)


@dataclass(frozen=True)
class ErrorPattern:
    error_id: str
    name_en: str
    name_zh: str
    skills: tuple[str, ...]
    description: str = ""

    def applies_to(self, skill_id: str) -> bool:
        return any(skill_matches(entry, skill_id) for entry in self.skills)

    @property
    def is_general(self) -> bool:
        """Belongs to a strand or to everything rather than to named skills."""
        return any(is_wildcard(entry) for entry in self.skills)


@dataclass(frozen=True)
class GuideObjective:
    ref: str                           # "CP-1.4"
    part: str                          # KS3 | CP | M1 | M2
    strand: str
    unit_no: str
    unit: str
    text: str
    status: str                        # foundation | non-foundation | enrichment
    remarks: str = ""


@dataclass
class Taxonomy:
    skills: dict[str, Skill] = field(default_factory=dict)
    errors: dict[str, ErrorPattern] = field(default_factory=dict)
    objectives: dict[str, GuideObjective] = field(default_factory=dict)

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
        return [e for e in self.errors.values() if e.applies_to(skill_id)]

    def error_fits(self, error_id: str, skill_ids: Iterable[str]) -> bool:
        """Can a question using these skills expose this error?

        Yes if the error belongs to one of the skills or to a skill any of
        them rests on: a simultaneous-equations question still exposes a
        transposing sign error, because solving a linear equation is a
        prerequisite of it.
        """
        pattern = self.errors[error_id]
        for skill_id in skill_ids:
            if pattern.applies_to(skill_id):
                return True
            if skill_id in self.skills and any(pattern.applies_to(pre) for pre in
                                               self.prerequisites_closure(skill_id)):
                return True
        return False

    def skills_for_objective(self, ref: str) -> list[Skill]:
        return [s for s in self.skills.values() if ref in s.guide_ref]

    def uncovered_objectives(self) -> list[GuideObjective]:
        """Assessed Guide objectives that no skill names (Enrichment ones are not assessed)."""
        covered = {ref for s in self.skills.values() for ref in s.guide_ref}
        return [o for o in self.objectives.values()
                if o.ref not in covered and o.status != "enrichment"]

    def unique_skill_for(self, wrong_id: str) -> Optional[str]:
        """The one known skill whose unit and slug match a wrong id, if any.

        The Analyzer's commonest slip is the strand prefix (ms.lineq.solve for
        na.lineq.solve). When exactly one skill shares the rest of the id the
        intent is unambiguous and the id can be corrected rather than rejected.
        """
        parts = wrong_id.split(".")
        if len(parts) != 3 or wrong_id in self.skills:
            return None
        tail = "." + ".".join(parts[1:])
        matches = [s for s in self.skills if s.endswith(tail)]
        return matches[0] if len(matches) == 1 else None

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
            guide_ref=_split(row.get("guide_ref", "")),
        ))
    return skills


def read_guide_objectives(path: Path = GUIDE_OBJECTIVES_CSV) -> list[GuideObjective]:
    status = {"": "foundation", "N": "non-foundation", "E": "enrichment"}
    return [GuideObjective(
        ref=f"{row['part'].strip()}-{row['obj'].strip()}",
        part=row["part"].strip(), strand=row["strand"].strip(), unit_no=row["unit_no"].strip(),
        unit=row["unit"].strip(), text=row["text"].strip(),
        status=status[row.get("nf", "").strip()], remarks=(row.get("remarks") or "").strip(),
    ) for row in _rows(path)]


def read_error_patterns(path: Path = ERROR_PATTERNS_CSV) -> list[ErrorPattern]:
    return [ErrorPattern(
        error_id=row["error_id"].strip(),
        name_en=row["name_en"].strip(),
        name_zh=row["name_zh"].strip(),
        skills=_split(row.get("skills", "")),
        description=(row.get("description") or "").strip(),
    ) for row in _rows(path)]


# --- checking -----------------------------------------------------------------

def validate(skills: Iterable[Skill], errors: Iterable[ErrorPattern],
             objectives: Optional[Iterable[GuideObjective]] = None) -> list[str]:
    """Every way the files can be wrong, as plain sentences.

    With `objectives`, every guide_ref must name one of them and the
    Foundation / Non-foundation / Enrichment flag must agree with them.
    """
    problems: list[str] = []
    skills, errors = list(skills), list(errors)
    ids = [s.skill_id for s in skills]
    known = set(ids)
    guide = {o.ref: o for o in objectives} if objectives is not None else None

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
        if compulsory and s.foundation is None and s.in_guide:
            problems.append(f"skill {s.skill_id} is in the Guide but has no foundation flag")
        if not compulsory and s.foundation is not None:
            problems.append(f"skill {s.skill_id} is {STRANDS[s.strand]}, where the "
                            f"Foundation / Non-foundation split does not apply")
        if compulsory and not s.guide_ref:
            problems.append(f"skill {s.skill_id} has no guide_ref (an objective, KS2 or ext)")
        for ref in s.guide_ref:
            if ref in ("ext", "KS2"):
                continue
            if not _GUIDE_REF.match(ref):
                problems.append(f"skill {s.skill_id} has guide_ref {ref!r}, not <part>-<n.m>")
            elif guide is not None and ref not in guide:
                problems.append(f"skill {s.skill_id} refers to Guide objective {ref}, which "
                                f"is not in guide_objectives.csv")
        if guide is not None and compulsory:
            expected = _expected_flag(s, guide)
            if expected and FOUNDATION.get(expected) != s.foundation:
                problems.append(f"skill {s.skill_id} is flagged {s.foundation or 'blank'} but "
                                f"its Guide objectives say {FOUNDATION[expected]}")
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
            if skill_id not in known and not is_wildcard(skill_id):
                problems.append(f"error {e.error_id} refers to {skill_id}, which does not exist")
        if not e.name_en or not e.name_zh:
            problems.append(f"error {e.error_id} is missing an English or Chinese name")

    return sorted(set(problems))


def _expected_flag(skill: Skill, guide: dict[str, GuideObjective]) -> str:
    """F if any named objective is Foundation, else N, else E; "" when none is named."""
    kinds = {guide[r].status for r in skill.guide_ref if r in guide}
    if "foundation" in kinds or ("KS2" in skill.guide_ref and not kinds):
        return "F"
    if "non-foundation" in kinds:
        return "N"
    if "enrichment" in kinds:
        return "E"
    return ""


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
                  errors_path: Path = ERROR_PATTERNS_CSV,
                  objectives_path: Optional[Path] = GUIDE_OBJECTIVES_CSV) -> Taxonomy:
    """All files, checked. Raises with every problem if there are any."""
    skills = read_skills(skills_path)
    errors = read_error_patterns(errors_path)
    objectives = read_guide_objectives(objectives_path) if objectives_path else []
    problems = validate(skills, errors, objectives if objectives_path else None)
    if problems:
        raise ValueError("The taxonomy has problems:\n  " + "\n  ".join(problems))
    return Taxonomy({s.skill_id: s for s in skills}, {e.error_id: e for e in errors},
                    {o.ref: o for o in objectives})
