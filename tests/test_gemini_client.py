"""Tests for response handling. No network, no API key - fake responses only."""

import pytest

from app.errors import EmptyResponseError, ExtractionError, TruncatedResponseError
from app.gemini_client import finish_reason_name, is_retryable_error, parse_response
from app.schemas import QuestionExtractionPayload


class FakeReason:
    def __init__(self, name):
        self.name = name


class FakeCandidate:
    def __init__(self, finish_reason=None):
        self.finish_reason = finish_reason


class FakeResponse:
    def __init__(self, finish_reason=None, parsed=None, text=None, text_raises=False):
        self.candidates = [FakeCandidate(finish_reason)] if finish_reason is not None else []
        self.parsed = parsed
        self._text = text
        self._text_raises = text_raises

    @property
    def text(self):
        if self._text_raises:
            raise ValueError("no text parts in response")
        return self._text


class FakeApiError(Exception):
    def __init__(self, code):
        super().__init__(f"api error {code}")
        self.code = code


VALID_JSON = '{"questions": [{"source_question_id": "1(a)", "page_start": 1, ' \
             '"page_end": 1, "question_text": "Factorise 1 - 225x\\u00b2."}]}'


# --- retry predicate --------------------------------------------------------

@pytest.mark.parametrize("code", [408, 429, 500, 502, 503, 504])
def test_transient_api_errors_are_retryable(code):
    assert is_retryable_error(FakeApiError(code)) is True


@pytest.mark.parametrize("code", [400, 401, 403, 404, 422])
def test_client_errors_are_not_retryable(code):
    assert is_retryable_error(FakeApiError(code)) is False


def test_network_errors_are_retryable():
    assert is_retryable_error(TimeoutError("timed out")) is True
    assert is_retryable_error(ConnectionError("reset")) is True


def test_unrelated_errors_are_not_retryable():
    assert is_retryable_error(ValueError("bad schema")) is False


# --- finish_reason reading --------------------------------------------------

def test_finish_reason_reads_enum_name():
    assert finish_reason_name(FakeResponse(FakeReason("MAX_TOKENS"))) == "MAX_TOKENS"


def test_finish_reason_reads_dotted_string():
    assert finish_reason_name(FakeResponse("FinishReason.STOP")) == "STOP"


def test_finish_reason_is_none_without_candidates():
    assert finish_reason_name(FakeResponse()) is None


# --- parse_response ---------------------------------------------------------

def test_truncated_response_raises_a_clear_error():
    response = FakeResponse(FakeReason("MAX_TOKENS"), text='{"questions": [{"sou')
    with pytest.raises(TruncatedResponseError) as exc:
        parse_response(response, QuestionExtractionPayload)
    assert "GEMINI_MAX_OUTPUT_TOKENS" in str(exc.value)


@pytest.mark.parametrize("reason", ["SAFETY", "BLOCKLIST", "PROHIBITED_CONTENT", "RECITATION"])
def test_blocked_response_raises_extraction_error(reason):
    with pytest.raises(ExtractionError):
        parse_response(FakeResponse(FakeReason(reason)), QuestionExtractionPayload)


def test_empty_text_raises_instead_of_confusing_type_error():
    with pytest.raises(EmptyResponseError):
        parse_response(FakeResponse(FakeReason("STOP"), text=None), QuestionExtractionPayload)


def test_blank_text_raises():
    with pytest.raises(EmptyResponseError):
        parse_response(FakeResponse(FakeReason("STOP"), text="   "), QuestionExtractionPayload)


def test_text_property_raising_is_treated_as_empty():
    response = FakeResponse(FakeReason("STOP"), text_raises=True)
    with pytest.raises(EmptyResponseError):
        parse_response(response, QuestionExtractionPayload)


def test_parsed_payload_is_returned_directly():
    payload = QuestionExtractionPayload(questions=[])
    assert parse_response(FakeResponse(FakeReason("STOP"), parsed=payload),
                          QuestionExtractionPayload) is payload


def test_text_is_parsed_when_parsed_is_missing():
    response = FakeResponse(FakeReason("STOP"), text=VALID_JSON)
    payload = parse_response(response, QuestionExtractionPayload)
    assert payload.questions[0].source_question_id == "1(a)"
    assert payload.questions[0].question_text == "Factorise 1 - 225x²."
