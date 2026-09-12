"""Ingestion error types.

The pipeline needs to tell three things apart:
  * the PDF could not be read at all            -> caller's fault, fix the file
  * Gemini could not return usable JSON         -> retry or split the PDF
  * Gemini returned JSON but the content is bad -> a ValidationIssue, not an error
Only the first two are exceptions. Bad content is reported as issues so the
questions that WERE extracted are still saved for inspection.
"""


class IngestionError(Exception):
    """Base class for every error this system raises on purpose."""


class ExtractionError(IngestionError):
    """Gemini did not return usable JSON."""


class TruncatedResponseError(ExtractionError):
    """Gemini hit the output token limit, so the JSON is incomplete."""


class EmptyResponseError(ExtractionError):
    """Gemini returned no JSON at all."""
