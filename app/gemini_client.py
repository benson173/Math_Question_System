"""Call Gemini and return parsed JSON. Nothing more.

This file does not decide whether a question is right, write to a database,
edit the prompt, or judge difficulty. It only gets structured JSON back, and
fails with a message that says what went wrong.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from google import genai
from google.genai import types
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.config import load_settings
from app.errors import EmptyResponseError, ExtractionError, TruncatedResponseError


PDF_MIME_TYPE = "application/pdf"

# Below this size the PDF rides along in the request itself. Above it, the Files
# API is used and the upload is deleted afterwards. Inlining avoids a second
# round trip and leaves nothing behind to clean up.
INLINE_MAX_BYTES = 15 * 1024 * 1024

# Transient failures worth another attempt: rate limits and server-side errors.
RETRYABLE_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})
MAX_ATTEMPTS = 4

# finish_reason values that mean the model stopped for a reason other than
# "finished the answer".
_TRUNCATED_REASONS = frozenset({"MAX_TOKENS"})
_BLOCKED_REASONS = frozenset({"SAFETY", "BLOCKLIST", "PROHIBITED_CONTENT", "RECITATION"})


def read_prompt(prompt_path: str | Path) -> str:
    return Path(prompt_path).read_text(encoding="utf-8")


def is_retryable_error(exc: BaseException) -> bool:
    """True for failures that a later attempt might survive."""
    for attribute in ("code", "status_code"):
        code = getattr(exc, attribute, None)
        if isinstance(code, int) and code in RETRYABLE_STATUS_CODES:
            return True
    return isinstance(exc, (TimeoutError, ConnectionError))


def usage_from(response: Any) -> dict[str, int | None]:
    """Token counts from a response, or Nones when the SDK gives none."""
    usage = getattr(response, "usage_metadata", None)
    return {
        "input_tokens": getattr(usage, "prompt_token_count", None),
        "output_tokens": getattr(usage, "candidates_token_count", None),
    }


def prompt_sha256(prompt_path: str | Path) -> str:
    """Twelve hex characters identifying the exact prompt text used."""
    import hashlib
    return hashlib.sha256(Path(prompt_path).read_bytes()).hexdigest()[:12]


def finish_reason_name(response: Any) -> str | None:
    """Read the first candidate's finish_reason as a plain upper-case name."""
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        return None
    reason = getattr(candidates[0], "finish_reason", None)
    if reason is None:
        return None
    name = getattr(reason, "name", None) or str(reason)
    return name.rsplit(".", 1)[-1].upper()


def parse_response(response: Any, schema) -> Any:
    """Turn a Gemini response into a schema instance, or say why it cannot.

    Without this, a response cut off at the token limit reaches Pydantic as half
    a JSON document and surfaces as an unreadable ValidationError.
    """
    reason = finish_reason_name(response)

    if reason in _TRUNCATED_REASONS:
        raise TruncatedResponseError(
            "Gemini hit its output token limit, so the JSON is incomplete. "
            "Split the PDF into smaller files, or raise GEMINI_MAX_OUTPUT_TOKENS."
        )

    if reason in _BLOCKED_REASONS:
        raise ExtractionError(f"Gemini blocked the response (finish_reason={reason}).")

    parsed = getattr(response, "parsed", None)
    if parsed is not None:
        return parsed

    try:
        text = response.text
    except Exception:  # the SDK raises when a response carries no text parts
        text = None

    if not text or not text.strip():
        raise EmptyResponseError(
            f"Gemini returned no JSON (finish_reason={reason or 'unknown'})."
        )

    return schema.model_validate_json(text)


class GeminiClient:
    def __init__(self):
        self.settings = load_settings()
        if not self.settings.gemini_api_key:
            raise ValueError("Missing GEMINI_API_KEY in .env")
        if not self.settings.gemini_extractor_model:
            raise ValueError("Missing GEMINI_EXTRACTOR_MODEL in .env")

        # Filled after every call, read by whoever builds the run record.
        self.last_usage: dict[str, int | None] = {"input_tokens": None, "output_tokens": None}

        self.client = genai.Client(
            api_key=self.settings.gemini_api_key,
            http_options=types.HttpOptions(
                timeout=int(self.settings.gemini_timeout_seconds * 1000),
            ),
        )

    def extract_pdf_json(
        self,
        pdf_path: str | Path,
        prompt_path: str | Path,
        schema,
        pdf_bytes: bytes | None = None,
    ):
        prompt = read_prompt(prompt_path)
        data = pdf_bytes if pdf_bytes is not None else Path(pdf_path).read_bytes()

        if len(data) <= INLINE_MAX_BYTES:
            part = types.Part.from_bytes(data=data, mime_type=PDF_MIME_TYPE)
            return self._generate(part, prompt, schema)

        uploaded = self.client.files.upload(file=str(pdf_path))
        try:
            return self._generate(uploaded, prompt, schema)
        finally:
            self._delete_quietly(uploaded)

    def generate_json(self, prompt: str, schema):
        """A text-only structured call - the Analyzer sends questions, not a PDF."""
        return self._generate_contents([prompt], schema)

    def _delete_quietly(self, uploaded: Any) -> None:
        """Remove an uploaded file so repeated batches do not fill the quota."""
        name = getattr(uploaded, "name", None)
        if not name:
            return
        try:
            self.client.files.delete(name=name)
        except Exception as exc:
            print(f"Warning: could not delete uploaded file {name}: {exc}")

    def _generate(self, pdf_part: Any, prompt: str, schema):
        return self._generate_contents([pdf_part, prompt], schema)

    @retry(
        retry=retry_if_exception(is_retryable_error),
        stop=stop_after_attempt(MAX_ATTEMPTS),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        reraise=True,
    )
    def _generate_contents(self, contents: list, schema):
        config_kwargs: dict[str, Any] = {
            "temperature": 0.0,
            "response_mime_type": "application/json",
            "response_schema": schema,
        }
        if self.settings.gemini_max_output_tokens > 0:
            config_kwargs["max_output_tokens"] = self.settings.gemini_max_output_tokens

        response = self.client.models.generate_content(
            model=self.settings.gemini_extractor_model,
            contents=contents,
            config=types.GenerateContentConfig(**config_kwargs),
        )
        self.last_usage = usage_from(response)
        return parse_response(response, schema)
