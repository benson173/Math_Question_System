"""A stable identity for every question, across extraction runs.

`questions.id` is new on every run. Anything that must survive a re-extraction
- an RPDICE analysis, a student's answer - cannot hang off it. What does not
change when a paper is re-extracted is the paper's content and the number the
question is printed with, so the key is built from exactly those two:

    <first 12 hex of the PDF's sha256>:<source_question_id>

    b584940bfebb:17(a)

Twelve hex characters is the same prefix the JSON file names use, and 48 bits
is far more than a question bank will ever need to stay unique.
"""

from __future__ import annotations


KEY_HASH_LENGTH = 12


def paper_key(sha256: str) -> str:
    if not sha256 or len(sha256) < KEY_HASH_LENGTH:
        raise ValueError(f"sha256 too short for a paper key: {sha256!r}")
    return sha256[:KEY_HASH_LENGTH].lower()


def question_key(sha256: str, source_question_id: str) -> str:
    qid = (source_question_id or "").strip()
    if not qid:
        raise ValueError("A question with no source_question_id has no key.")
    return f"{paper_key(sha256)}:{qid}"


def split_question_key(key: str) -> tuple[str, str]:
    """The paper key and the question id a key was built from."""
    paper, sep, qid = key.partition(":")
    if not sep or len(paper) != KEY_HASH_LENGTH or not qid:
        raise ValueError(f"Not a question key: {key!r}")
    return paper, qid
