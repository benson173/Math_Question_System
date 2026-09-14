"""Which form a paper is for.

Two places can say it: the file name (F4-2024-mock.pdf, 2526_1st_S4MATH1.pdf)
and the paper itself (中四 / S.4 / Form 4 on the cover, which Gemini copies out
as level_text). This module turns either into one canonical code, so nothing
downstream ever has to compare "中四" with "S.4".

Codes are F1 to F6 - Form 1 to Form 6, 中一至中六. S4, 中四, Form 4, Secondary 4
and Grade 10 all normalise to F4.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


LEVELS = tuple(f"F{n}" for n in range(1, 7))

_CN_DIGIT = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6}

# Not preceded by a letter or digit, not followed by a digit: "S4MATH1" and
# "2526_1st_S4" match, "45" inside a year and "S45" do not.
_EDGE = r"(?<![A-Za-z0-9])"
_END = r"(?![0-9])"

# "Form 4", "Secondary 4", "Sec 4", "F.4", "S4", "F 4".
_WORD = re.compile(_EDGE + r"(?:form|secondary|sec)\.?\s?([1-6])" + _END, re.I)
# The README asks for lower-case file names, so "s4-2024-mock.pdf" has to work
# as well as "S4". The edge guard is what keeps "maths4" from matching.
_LETTER = re.compile(_EDGE + r"[SF]\.?\s?([1-6])" + _END, re.I)
# 其中一個 ("one of them") is not 中一. 中一至中三 names two, so nothing is chosen.
_CHINESE = re.compile(r"(?<![其當集])中([一二三四五六])(?:年級|級)?")
# US grades: Grade 7 is Form 1.
_GRADE = re.compile(_EDGE + r"grade\s?(7|8|9|1[0-2])" + _END, re.I)


def find_levels(text: str) -> list[str]:
    """Every form named in the text, in printed order, without repeats."""
    if not text:
        return []
    found: list[tuple[int, str]] = []

    for pattern in (_WORD, _LETTER):
        for match in pattern.finditer(text):
            found.append((match.start(), f"F{int(match.group(1))}"))
    for match in _CHINESE.finditer(text):
        found.append((match.start(), f"F{_CN_DIGIT[match.group(1)]}"))
    for match in _GRADE.finditer(text):
        found.append((match.start(), f"F{int(match.group(1)) - 6}"))

    ordered: list[str] = []
    for _, code in sorted(found):
        if code not in ordered:
            ordered.append(code)
    return ordered


def parse_level(text: Optional[str]) -> Optional[str]:
    """The one form the text names, or None if it names none or several.

    Two different forms in one string ("中一至中三") is not a paper level, so
    nothing is returned rather than picking the first and being wrong.
    """
    levels = find_levels(text or "")
    return levels[0] if len(levels) == 1 else None


def level_from_filename(file_name: str) -> Optional[str]:
    return parse_level(file_name)


def level_from_paper(level_text: Optional[str]) -> Optional[str]:
    return parse_level(level_text)


@dataclass(frozen=True)
class ResolvedLevel:
    level: Optional[str]
    source: Optional[str]          # "filename" | "paper" | None


def resolve_level(file_name: str, level_text: Optional[str]) -> ResolvedLevel:
    """The file name first, then what the paper prints.

    The file name wins because a person chose it deliberately and can fix it by
    renaming; the printed text is one model's reading of one cover page. A
    disagreement is reported by the validator, not silently settled.
    """
    from_name = level_from_filename(file_name)
    if from_name:
        return ResolvedLevel(from_name, "filename")
    from_paper = level_from_paper(level_text)
    if from_paper:
        return ResolvedLevel(from_paper, "paper")
    return ResolvedLevel(None, None)
