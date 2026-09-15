"""Which part of the syllabus a paper belongs to: Compulsory, M1 or M2.

HKDSE Mathematics is a Compulsory Part plus two optional Extended Part modules:

    M1  Module 1 (Calculus and Statistics)   微積分與統計
    M2  Module 2 (Algebra and Calculus)      代數與微積分

A question from M1 and a question from the Compulsory Part are not comparable -
different syllabus, different students, different skill set - so the module has
to be recorded at ingestion, the same way the form is.

Read from the file name first, then from what the paper prints on its cover.
Nothing said anywhere means "compulsory", because that is what the overwhelming
majority of papers are; the source is recorded so a wrong default is visible.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Optional


MODULES = ("compulsory", "M1", "M2")

# "M1", "M 1", "M.1" as a token of its own. The guard matters: "S4MATH1" is
# Maths paper 1, not M1 - there the M is followed by A - and a bare digit
# before ("2526M2") is too ambiguous to trust, so both block the match.
_SHORT = re.compile(r"(?<![A-Za-z0-9])M[.\s]?([12])(?![0-9])", re.IGNORECASE)
# The two compact spellings the guard above would otherwise refuse:
# "MATHM1" (maths, module 1) and "S6M2" (Form 6, module 2).
_COMPACT = re.compile(r"MATHS?[-_\s]?M[.\s]?([12])(?![0-9])", re.IGNORECASE)
_WITH_FORM = re.compile(r"(?<![A-Za-z0-9])[SF][1-6][-_\s]?M[.\s]?([12])(?![0-9])",
                        re.IGNORECASE)
_WORD = re.compile(r"(?<![A-Za-z])module[-_\s]?([12])(?![0-9])", re.IGNORECASE)
_CHINESE = re.compile(r"單元\s?([一二12])")
_CN_DIGIT = {"一": "1", "二": "2", "1": "1", "2": "2"}
# The module names, which a cover page prints in full.
_BY_NAME = (
    (re.compile(r"calculus\s+and\s+statistics", re.IGNORECASE), "M1"),
    (re.compile(r"微積分\s*(?:與|及|和)\s*統計"), "M1"),
    (re.compile(r"algebra\s+and\s+calculus", re.IGNORECASE), "M2"),
    (re.compile(r"代數\s*(?:與|及|和)\s*微積分"), "M2"),
)
# Says "Extended Part" without saying which module.
_EXTENDED = re.compile(r"extended\s+part|延伸部分", re.IGNORECASE)


def find_modules(text: str) -> list[str]:
    """Every module named in the text, in order, without repeats."""
    if not text:
        return []
    found: list[tuple[int, str]] = []
    for pattern in (_SHORT, _COMPACT, _WITH_FORM):
        for match in pattern.finditer(text):
            found.append((match.start(), f"M{match.group(1)}"))
    for match in _WORD.finditer(text):
        found.append((match.start(), f"M{match.group(1)}"))
    for match in _CHINESE.finditer(text):
        found.append((match.start(), f"M{_CN_DIGIT[match.group(1)]}"))
    for pattern, module in _BY_NAME:
        for match in pattern.finditer(text):
            found.append((match.start(), module))

    ordered: list[str] = []
    for _, module in sorted(found):
        if module not in ordered:
            ordered.append(module)
    return ordered


def parse_module(text: Optional[str]) -> Optional[str]:
    """The one module the text names, or None if it names none or several."""
    modules = find_modules(text or "")
    return modules[0] if len(modules) == 1 else None


def mentions_extended_part(text: Optional[str]) -> bool:
    return bool(_EXTENDED.search(text or ""))


@dataclass(frozen=True)
class ResolvedModule:
    module: str
    source: str            # "filename" | "paper" | "sidecar" | "default"


def resolve_module(file_name: str, module_text: Optional[str] = None,
                   stated: Optional[str] = None) -> ResolvedModule:
    """A stated module wins, then the file name, then the paper, then the default."""
    if stated:
        return ResolvedModule(stated, "sidecar")
    from_name = parse_module(file_name)
    if from_name:
        return ResolvedModule(from_name, "filename")
    from_paper = parse_module(module_text)
    if from_paper:
        return ResolvedModule(from_paper, "paper")
    return ResolvedModule("compulsory", "default")
