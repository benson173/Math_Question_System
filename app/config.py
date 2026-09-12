from dataclasses import dataclass
from dotenv import load_dotenv
from functools import lru_cache
import os


DEFAULT_TIMEOUT_SECONDS = 300.0
# 0 means "do not send max_output_tokens at all" - let the model use its own
# default. Setting a value the chosen model does not support is an API error,
# so this stays opt-in.
DEFAULT_MAX_OUTPUT_TOKENS = 0

# Diagram rendering
DEFAULT_DIAGRAM_DPI = 200
DEFAULT_RENDER_DIAGRAMS = True
DEFAULT_REPAIR_EXTRACTION = True


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str
    gemini_extractor_model: str
    supabase_url: str
    supabase_secret_key: str
    extraction_version: str
    question_object_version: str
    gemini_timeout_seconds: float
    gemini_max_output_tokens: int
    render_diagrams: bool
    repair_extraction: bool
    diagram_dpi: int


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false, got {raw!r}")


def _env_number(name: str, default: float, cast):
    raw = os.getenv(name, "").strip()
    if not raw:
        return cast(default)
    try:
        return cast(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, got {raw!r}") from exc


@lru_cache(maxsize=1)
def load_settings() -> Settings:
    """Read .env once per process.

    Cached because both GeminiClient and Repository need settings, and there is
    no reason to re-parse .env for each. Call load_settings.cache_clear() if you
    change the environment inside a test.
    """
    load_dotenv()

    return Settings(
        gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
        gemini_extractor_model=os.getenv("GEMINI_EXTRACTOR_MODEL", ""),
        supabase_url=os.getenv("SUPABASE_URL", ""),
        supabase_secret_key=os.getenv("SUPABASE_SECRET_KEY", ""),
        extraction_version=os.getenv("EXTRACTION_VERSION", "QEE_v1"),
        question_object_version=os.getenv("QUESTION_OBJECT_VERSION", "QOS_v1"),
        gemini_timeout_seconds=_env_number(
            "GEMINI_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS, float),
        gemini_max_output_tokens=_env_number(
            "GEMINI_MAX_OUTPUT_TOKENS", DEFAULT_MAX_OUTPUT_TOKENS, int),
        render_diagrams=_env_flag("RENDER_DIAGRAMS", DEFAULT_RENDER_DIAGRAMS),
        repair_extraction=_env_flag("REPAIR_EXTRACTION", DEFAULT_REPAIR_EXTRACTION),
        diagram_dpi=_env_number("DIAGRAM_DPI", DEFAULT_DIAGRAM_DPI, int),
    )
