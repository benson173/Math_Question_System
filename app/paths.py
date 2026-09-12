"""Project paths, anchored to the repository root.

Every path used by the system is resolved from this file's location, so the
scripts work no matter which directory you run them from.
"""

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

PROMPTS_DIR = PROJECT_ROOT / "prompts"
PROMPT_DOCUMENT_EXTRACTOR_V1 = PROMPTS_DIR / "document_extractor_v1.txt"

DATA_DIR = PROJECT_ROOT / "data"
EXTRACTED_DIR = DATA_DIR / "extracted"
HISTORY_DIR = DATA_DIR / "history"
DIAGRAMS_DIR = DATA_DIR / "diagrams"

INBOX_PDF_DIR = PROJECT_ROOT / "inbox" / "pdf"
PROCESSED_PDF_DIR = PROJECT_ROOT / "processed" / "pdf"
FAILED_PDF_DIR = PROJECT_ROOT / "failed" / "pdf"
