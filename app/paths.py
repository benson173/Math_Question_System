"""Project paths, anchored to the repository root.

Every path used by the system is resolved from this file's location, so the
scripts work no matter which directory you run them from.
"""

from __future__ import annotations

from pathlib import Path
import re


# The PDF's own name becomes part of every output path, so it has to survive
# being a directory name and a Markdown link target. Letters and digits in any
# script are kept, so a Chinese title stays readable; spaces become hyphens and
# anything that would break a path or a link is dropped.
_UNSAFE_IN_NAME = re.compile(r"[\\/:*?\"<>|()\[\]{}#%&^$!`'~;,+=@\x00-\x1f]")
_WHITESPACE = re.compile(r"\s+")
_REPEATED_HYPHEN = re.compile(r"-{2,}")

MAX_STEM_LENGTH = 80


def safe_stem(name: str) -> str:
    """A file stem safe to use as a directory name and inside a Markdown link."""
    stem = Path(name).stem
    stem = _WHITESPACE.sub("-", stem)
    stem = _UNSAFE_IN_NAME.sub("", stem)
    stem = _REPEATED_HYPHEN.sub("-", stem).strip("-. ")
    return stem[:MAX_STEM_LENGTH].strip("-. ") or "document"


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def project_relative(path: str | Path) -> str:
    """A path as stored in JSON and the database: relative to the repo root.

    An absolute /Users/benson/... path is true on one machine only. Paths
    outside the project stay absolute, because there is nothing better.
    """
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(resolved)


def project_absolute(path: str | Path) -> Path:
    """The reverse: a stored path back to a real one on this machine."""
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate

PROMPTS_DIR = PROJECT_ROOT / "prompts"
PROMPT_DOCUMENT_EXTRACTOR_V1 = PROMPTS_DIR / "document_extractor_v1.txt"
PROMPT_MARKING_SCHEME_V1 = PROMPTS_DIR / "marking_scheme_v1.txt"
PROMPT_ANALYZER_V1 = PROMPTS_DIR / "analyzer_v1.txt"
PROMPT_SOLVER_V1 = PROMPTS_DIR / "solver_v1.txt"
PROMPT_CRITIC_V1 = PROMPTS_DIR / "critic_v1.txt"

DATA_DIR = PROJECT_ROOT / "data"
EXTRACTED_DIR = DATA_DIR / "extracted"
HISTORY_DIR = DATA_DIR / "history"
DIAGRAMS_DIR = DATA_DIR / "diagrams"
ANALYSES_DIR = DATA_DIR / "analyses"
GOLD_DIR = PROJECT_ROOT / "taxonomy" / "golden"
RPDICE_GOLD_CSV = GOLD_DIR / "rpdice_gold.csv"

INBOX_PDF_DIR = PROJECT_ROOT / "inbox" / "pdf"
PROCESSED_PDF_DIR = PROJECT_ROOT / "processed" / "pdf"
FAILED_PDF_DIR = PROJECT_ROOT / "failed" / "pdf"
