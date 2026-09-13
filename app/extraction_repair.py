"""Repair a fault the prompt cannot reliably prevent.

Sub-questions of one parent repeat their shared stem so each stands alone. Now
and then the model lets one part's own question slip into that shared stem, so
every sibling carries a question that is not its own. Asked three times for the
same paper, the model produced it, fixed it, then produced it again - so this is
detected and undone here rather than argued about in the prompt.

The repair is deliberately narrow: it fires only when the last sentence of the
stem shared by all siblings is exactly one sibling's entire question. Anything
it changes is recorded in that question's extraction_notes, so nothing is
altered silently.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from app.schemas import ExtractedDocument, ExtractedQuestion


# "19(a)" -> "19";  "18(a)(ii)" -> "18(a)";  "7" -> None
_TRAILING_PART = re.compile(r"^(.+?)\s*\([^()]*\)\s*$")

_SENTENCE_END = "。？！"
MIN_STEM_SENTENCE = 8

# A LaTeX command whose backslash the model failed to escape in its JSON comes
# back as the control character that escape denotes: "\\frac" is written as
# "\frac", and the JSON decoder reads \f as a form feed, leaving FF + "rac".
#
# JSON defines only \b \f \n \r \t (plus \" \\ \/ \uXXXX), so those are the
# only commands that can be damaged this way - "\vec" or "\alpha" would make
# the whole response invalid JSON and fail loudly instead.
#
# Of the five, only backspace and form feed can never legitimately appear in a
# question, so only those are rewritten. Tab, newline and carriage return begin
# \times, \neq and \rho but are also ordinary whitespace, so they are reported
# rather than guessed at.
EATEN_BACKSLASH = {
    "\x0c": "f",   # \frac, \forall, \fbox
    "\x08": "b",   # \beta, \bar, \binom
}


@dataclass
class LatexRepair:
    source_question_id: str
    line: str


@dataclass
class ControlCharacterRepair:
    source_question_id: str
    character: str
    restored: str
    count: int


@dataclass
class StemRepair:
    parent: str
    removed: str
    question_ids: list[str]
    owner: str


def parent_id(source_question_id: str) -> str | None:
    """The id of the question a part belongs to, or None if it is not a part."""
    match = _TRAILING_PART.match(source_question_id.strip())
    return match.group(1).strip() if match else None


def sibling_groups(questions: list[ExtractedQuestion]) -> dict[str, list[ExtractedQuestion]]:
    groups: dict[str, list[ExtractedQuestion]] = {}
    for question in questions:
        parent = parent_id(question.source_question_id)
        if parent:
            groups.setdefault(parent, []).append(question)
    return {parent: members for parent, members in groups.items() if len(members) >= 2}


def common_prefix(texts: list[str]) -> str:
    if not texts:
        return ""
    prefix = texts[0]
    for text in texts[1:]:
        limit = min(len(prefix), len(text))
        cut = limit
        for index in range(limit):
            if prefix[index] != text[index]:
                cut = index
                break
        prefix = prefix[:cut]
        if not prefix:
            break
    return prefix


def trim_to_sentence_end(text: str) -> str:
    """Cut back to just after the last sentence terminator."""
    last = max((text.rfind(char) for char in _SENTENCE_END), default=-1)
    return text[:last + 1] if last >= 0 else ""


def _normalise(text: str) -> str:
    return " ".join(text.split()).rstrip(_SENTENCE_END).strip()


def find_stem_contamination(questions: list[ExtractedQuestion]) -> list[StemRepair]:
    """Groups whose shared stem ends with one sibling's own question."""
    repairs: list[StemRepair] = []

    for parent, members in sorted(sibling_groups(questions).items()):
        stem = trim_to_sentence_end(common_prefix([q.question_text for q in members]))
        if not stem:
            continue

        sentences = [s for s in re.split(f"[{_SENTENCE_END}\n]+", stem) if s.strip()]
        if len(sentences) < 2:
            # Removing the only sentence would delete the whole stem.
            continue

        last_sentence = _normalise(sentences[-1])
        if len(last_sentence) < MIN_STEM_SENTENCE:
            continue

        owner = next(
            (q.source_question_id for q in members
             if _normalise(q.question_text[len(stem):]) == last_sentence),
            None,
        )
        if owner:
            repairs.append(StemRepair(
                parent=parent,
                removed=last_sentence,
                question_ids=[q.source_question_id for q in members],
                owner=owner,
            ))

    return repairs


def find_control_characters(text: str) -> dict[str, int]:
    """Control characters in a question, counted by character."""
    found: dict[str, int] = {}
    for character in text:
        if ord(character) < 32 and character != "\n":
            found[character] = found.get(character, 0) + 1
    return found


def restore_eaten_backslashes(text: str) -> tuple[str, dict[str, int]]:
    """Turn a control character back into the LaTeX command it came from.

    Returns the repaired text and what was restored, keyed by the letter that
    now follows the backslash.
    """
    restored: dict[str, int] = {}
    for character, letter in EATEN_BACKSLASH.items():
        count = text.count(character)
        if count:
            text = text.replace(character, "\\" + letter)
            restored[letter] = count
    return text, restored


def repair_control_characters(document: ExtractedDocument) -> list[ControlCharacterRepair]:
    """Undo unescaped LaTeX backslashes across a document, in place."""
    repairs: list[ControlCharacterRepair] = []

    for question in document.questions:
        repaired, restored = restore_eaten_backslashes(question.question_text)
        if not restored:
            continue

        question.question_text = repaired
        for letter, count in sorted(restored.items()):
            repairs.append(ControlCharacterRepair(
                source_question_id=question.source_question_id,
                character=letter,
                restored="\\" + letter,
                count=count,
            ))
            question.extraction_notes.append(
                f"Repaired: restored {count} unescaped backslash(es) before "
                f"{letter!r} - the JSON escape had eaten it."
            )

    return repairs


# A line that is nothing but maths: no CJK, not already delimited, and
# carrying at least one LaTeX command or braced script. Such a line is a
# displayed formula on its own, so wrapping the whole of it is unambiguous.
# LaTeX sitting inline inside a sentence is reported instead - where the maths
# ends inside prose is a guess, and a wrong guess reads worse than raw markup.
_CJK = re.compile(r"[\u3000-\u9fff\uff00-\uffef]")
_LATEX_COMMAND = re.compile(r"\\[a-zA-Z]{2,}")
_LATEX_SCRIPT = re.compile(r"[\^_]\{[^}\n]{1,30}\}")


def is_bare_formula_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped or _CJK.search(stripped):
        return False
    if "\\(" in stripped or "\\)" in stripped or "$" in stripped:
        return False
    return bool(_LATEX_COMMAND.search(stripped) or _LATEX_SCRIPT.search(stripped))


def wrap_bare_formulas(text: str) -> tuple[str, list[str]]:
    """Put \\( \\) around any line that is a formula and nothing else."""
    wrapped: list[str] = []
    lines = text.split("\n")
    for index, line in enumerate(lines):
        if not is_bare_formula_line(line):
            continue
        stripped = line.strip()
        indent = line[:len(line) - len(line.lstrip())]
        lines[index] = indent + "\\( " + stripped + " \\)"
        wrapped.append(stripped)
    return "\n".join(lines), wrapped


def repair_undelimited_latex(document: ExtractedDocument) -> list[LatexRepair]:
    """Delimit displayed formulas so they render, in place."""
    repairs: list[LatexRepair] = []

    for question in document.questions:
        repaired, wrapped = wrap_bare_formulas(question.question_text)
        if not wrapped:
            continue

        question.question_text = repaired
        for line in wrapped:
            repairs.append(LatexRepair(source_question_id=question.source_question_id,
                                       line=line))
        question.extraction_notes.append(
            f"Repaired: wrapped {len(wrapped)} displayed formula(s) in \\( \\) so they "
            "render; the model left them bare."
        )

    return repairs


def repair_shared_stems(document: ExtractedDocument) -> list[StemRepair]:
    """Strip the stray question out of each affected sibling's stem, in place."""
    repairs = find_stem_contamination(document.questions)
    if not repairs:
        return []

    by_id = {q.source_question_id: q for q in document.questions}

    for repair in repairs:
        members = [by_id[qid] for qid in repair.question_ids]
        stem = trim_to_sentence_end(common_prefix([q.question_text for q in members]))
        keep = trim_to_sentence_end(stem[:stem.rfind(repair.removed)])

        for question in members:
            question.question_text = (keep + question.question_text[len(stem):]).strip()
            question.extraction_notes.append(
                f"Repaired: removed {repair.removed!r} from the stem shared by "
                f"question {repair.parent}; it is {repair.owner}'s own question."
            )

    return repairs


# --- dependencies between parts --------------------------------------------
#
# "Hence", "由此", "利用 (a) 的結果": the printed words say a part builds on an
# earlier one. The prompt asks for depends_on, but a list the model leaves
# empty is indistinguishable from "no dependency", so the same cue words are
# read here and the list filled in when it is empty. Every fill is noted.

_ROMAN = re.compile(r"^[ivx]{1,4}$")
_CUE_WORDS = (r"利用|根據|使用|承|參考|按|由|[Uu]sing|[Ff]rom|[Bb]y|[Ii]n|"
              r"results?\s+of|[Pp]arts?")
_EXPLICIT_REFERENCE = re.compile(
    r"(?:" + _CUE_WORDS + r")\s*(?:the\s+)?(?:results?\s+(?:of|in)\s+)?(?:parts?\s+)?"
    r"\(([a-z]{1,2}|[ivx]{1,4})\)")
_HENCE = re.compile(r"(?<![A-Za-z])Hence(?![A-Za-z])|由此")


@dataclass
class DependencyRepair:
    source_question_id: str
    depends_on: list[str]
    reason: str


def _root_number(source_question_id: str) -> str:
    return source_question_id.split("(", 1)[0].strip()


def referenced_parts(text: str, source_question_id: str) -> list[str]:
    """Full ids of parts the text names with a cue word: "利用 (a)" -> "17(a")."""
    found: list[str] = []
    for match in _EXPLICIT_REFERENCE.finditer(text):
        token = match.group(1)
        if _ROMAN.match(token) and parent_id(source_question_id) \
                and "(" in (parent_id(source_question_id) or ""):
            target = f"{parent_id(source_question_id)}({token})"     # 18(a)(ii) -> 18(a)(i)
        else:
            target = f"{_root_number(source_question_id)}({token})"  # 17(b)     -> 17(a)
        if target != source_question_id and target not in found:
            found.append(target)
    return found


def says_hence(text: str) -> bool:
    return bool(_HENCE.search(text))


def previous_sibling(question: ExtractedQuestion, questions: list[ExtractedQuestion]) -> str | None:
    """The part printed just before this one under the same parent."""
    parent = parent_id(question.source_question_id)
    if parent is None:
        return None
    before: str | None = None
    for other in questions:
        if other is question:
            return before
        if parent_id(other.source_question_id) == parent:
            before = other.source_question_id
    return None


def repair_dependencies(document: ExtractedDocument) -> list[DependencyRepair]:
    """Fill an empty depends_on from the words that state it."""
    repairs: list[DependencyRepair] = []
    ids = {q.source_question_id for q in document.questions}

    for question in document.questions:
        if question.depends_on:
            continue
        explicit = [p for p in referenced_parts(question.question_text, question.source_question_id)
                    if p in ids]
        if explicit:
            question.depends_on = explicit
            reason = "named in the text"
        elif says_hence(question.question_text):
            before = previous_sibling(question, document.questions)
            if not before:
                continue
            question.depends_on = [before]
            reason = "'Hence' / '由此' refers to the part before"
        else:
            continue
        question.extraction_notes.append(
            f"depends_on filled from the text ({reason}): {', '.join(question.depends_on)}")
        repairs.append(DependencyRepair(question.source_question_id,
                                        list(question.depends_on), reason))
    return repairs
