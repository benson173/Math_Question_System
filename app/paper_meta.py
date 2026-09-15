"""What paper this is: year, term, exam type, paper number, school, topics.

Empirical difficulty has to be computed per cohort - a first-term Form 4 test
and a DSE mock are different populations - so the paper's context must be
recorded at ingestion, when it is still known. Two sources, sidecar first:

  1. A sidecar file next to the PDF, `<stem>.meta.txt`, one `key: value` per
     line. Anything can be stated here, including the school and the topics,
     which a file name never carries.
  2. The file name, for the fields it usually encodes: 2526_1st_S4MATH1.pdf
     says 2025-26, first term, paper 1.

Nothing here is required. A field that cannot be read stays null.
"""

from __future__ import annotations

from pathlib import Path
import re
from typing import Optional

from app.schemas import PaperMeta


SIDECAR_SUFFIX = ".meta.txt"

# "2025", "2025-26", "2025_26", "2025/26" and the compact school-year "2526".
_FULL_YEAR = re.compile(r"(?<!\d)(20\d\d)(?:[-_/](\d\d))?(?!\d)")
_COMPACT_YEAR = re.compile(r"(?<!\d)(\d\d)(\d\d)(?!\d)")

_TERM = [
    (re.compile(r"(?<![a-z])(1st|first)(?![a-z])", re.I), "1st"),
    (re.compile(r"(?<![a-z])(2nd|second)(?![a-z])", re.I), "2nd"),
    (re.compile(r"(?<![a-z])mid(?:[-_ ]?term|[-_ ]?year)?(?![a-z])", re.I), "mid"),
    (re.compile(r"(?<![a-z])final(?![a-z])", re.I), "final"),
    (re.compile(r"上學期|上期"), "1st"),
    (re.compile(r"下學期|下期"), "2nd"),
]

# Order matters: "dse-mock" is a mock, "mock exam" is a mock, "uniform test" a test.
_EXAM_TYPE = [
    (re.compile(r"(?<![a-z])mock(?![a-z])|模擬", re.I), "mock"),
    (re.compile(r"(?<![a-z])dse(?![a-z])", re.I), "dse"),
    (re.compile(r"(?<![a-z])(exam|examination)(?![a-z])|考試", re.I), "exam"),
    (re.compile(r"(?<![a-z])(test|ut|uniform)(?![a-z])|測驗|統測", re.I), "test"),
    (re.compile(r"(?<![a-z])quiz(?![a-z])|小測", re.I), "quiz"),
    (re.compile(r"(?<![a-z])(hw|homework|assignment|worksheet)(?![a-z])|功課|工作紙", re.I),
     "homework"),
]

# "paper1", "paper-2", "MATH1". A bare "P1" is not read: it is Paper 1 to
# some and Primary 1 to others.
_PAPER = re.compile(r"(?<![a-z])(?:paper|maths?)[-_ ]?([1-4])(?![0-9])", re.I)

FIELDS = ("year", "term", "exam_type", "paper_number", "school", "topics", "level",
          "module")


def _year(text: str) -> Optional[str]:
    full = _FULL_YEAR.search(text)
    if full:
        start, end = full.group(1), full.group(2)
        if end and int(end) == (int(start) + 1) % 100:
            return f"{start}-{end}"
        return start
    compact = _COMPACT_YEAR.search(text)
    if compact:
        first, second = int(compact.group(1)), int(compact.group(2))
        if 15 <= first <= 60 and second == first + 1:          # 2526 -> 2025-26
            return f"20{first:02d}-{second:02d}"
    return None


def _first_match(rules, text: str) -> Optional[str]:
    for pattern, value in rules:
        if pattern.search(text):
            return value
    return None


def meta_from_filename(file_name: str) -> PaperMeta:
    stem = Path(file_name).stem
    paper = _PAPER.search(stem)
    return PaperMeta(
        year=_year(stem),
        term=_first_match(_TERM, stem),
        exam_type=_first_match(_EXAM_TYPE, stem),
        paper_number=int(paper.group(1)) if paper else None,
        source="filename",
    )


def sidecar_path(pdf_path: str | Path) -> Path:
    path = Path(pdf_path)
    return path.with_name(path.stem + SIDECAR_SUFFIX)


def parse_sidecar(text: str) -> dict[str, object]:
    """`key: value` lines. Unknown keys are ignored, comments start with #."""
    values: dict[str, object] = {}
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        key = key.lower().replace("-", "_").replace(" ", "_")
        aliases = {"exam": "exam_type", "type": "exam_type", "paper": "paper_number",
                   "form": "level", "subject": "topics", "topic": "topics",
                   "part": "module", "extended": "module"}
        key = aliases.get(key, key)
        if key not in FIELDS or not value:
            continue
        if key == "topics":
            values[key] = [t.strip() for t in re.split(r"[,;、，]", value) if t.strip()]
        elif key == "paper_number":
            digits = re.search(r"\d+", value)
            if digits:
                values[key] = int(digits.group())
        else:
            values[key] = value
    return values


def meta_from_sidecar(pdf_path: str | Path) -> Optional[PaperMeta]:
    path = sidecar_path(pdf_path)
    if not path.exists():
        return None
    values = parse_sidecar(path.read_text(encoding="utf-8"))
    if not values:
        return None
    return PaperMeta(**{k: v for k, v in values.items() if k not in ("level", "module")},
                     source="sidecar")


def _sidecar_value(pdf_path: str | Path, field: str) -> Optional[str]:
    path = sidecar_path(pdf_path)
    if not path.exists():
        return None
    value = parse_sidecar(path.read_text(encoding="utf-8")).get(field)
    return str(value) if value else None


def sidecar_level(pdf_path: str | Path) -> Optional[str]:
    """A level stated in the sidecar, which outranks both file name and paper."""
    return _sidecar_value(pdf_path, "level")


def sidecar_module(pdf_path: str | Path) -> Optional[str]:
    """A module stated in the sidecar: "compulsory", "M1" or "M2"."""
    value = _sidecar_value(pdf_path, "module")
    if not value:
        return None
    from app.module import parse_module
    return parse_module(value) or (value if value.lower() == "compulsory" else None)


def resolve_paper_meta(pdf_path: str | Path) -> PaperMeta:
    """Sidecar fields first, the file name filling in whatever they leave."""
    from_name = meta_from_filename(Path(pdf_path).name)
    from_sidecar = meta_from_sidecar(pdf_path)
    if from_sidecar is None:
        return from_name

    merged = from_sidecar.model_dump()
    for field, value in from_name.model_dump().items():
        if merged.get(field) in (None, []) and field not in ("source",):
            merged[field] = value
    merged["source"] = "sidecar"
    return PaperMeta(**merged)
