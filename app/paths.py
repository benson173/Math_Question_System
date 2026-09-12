"""Project paths, anchored to the repository root.

Every path used by the system is resolved from this file's location, so the
scripts work no matter which directory you run them from.
"""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

PROMPTS_DIR = PROJECT_ROOT / "prompts"
PROMPT_DOCUMENT_EXTRACTOR_V1 = PROMPTS_DIR / "document_extractor_v1.txt"

DATA_DIR = PROJECT_ROOT / "data"
EXTRACTED_DIR = DATA_DIR / "extracted"

INBOX_PDF_DIR = PROJECT_ROOT / "inbox" / "pdf"
PROCESSED_PDF_DIR = PROJECT_ROOT / "processed" / "pdf"
FAILED_PDF_DIR = PROJECT_ROOT / "failed" / "pdf"
