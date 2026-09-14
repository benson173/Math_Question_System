"""The extract() path end to end, with a fake Gemini - the one path no other
test reaches, and where a missing method once hid until a real run."""

from __future__ import annotations

from app.document_extractor import DocumentExtractor
from app.schemas import ExtractedQuestion, QuestionExtractionPayload


class FakeGemini:
    last_usage = {"input_tokens": 1200, "output_tokens": 300}

    def __init__(self, level_text=None):
        self.level_text, self.calls = level_text, []

    def extract_pdf_json(self, pdf_path, prompt_path, schema, pdf_bytes=None):
        self.calls.append((pdf_path, prompt_path.name, schema.__name__, len(pdf_bytes or b"")))
        return QuestionExtractionPayload(
            questions=[ExtractedQuestion(source_question_id="1", page_start=1, page_end=1,
                                         question_text="因式分解 1 − 225x²。")],
            level_text=self.level_text)


class Settings:
    extraction_version = "QEE_v1"
    question_object_version = "QOS_v1"
    gemini_extractor_model = "m"


def extractor(gemini):
    built = DocumentExtractor.__new__(DocumentExtractor)
    built.gemini, built.settings = gemini, Settings()
    return built


def test_extract_returns_questions_source_and_run(write_pdf):
    pdf = write_pdf("2526_1st_S4MATH1.pdf", pages=3)
    gemini = FakeGemini(level_text="中四")
    result = extractor(gemini).extract(pdf)

    assert [q.source_question_id for q in result.document.questions] == ["1"]
    assert result.source.file_name == "2526_1st_S4MATH1.pdf"
    assert len(result.source.sha256) == 64 and result.source.page_count == 3
    assert result.run.model == "m" and result.run.input_tokens == 1200
    assert len(result.run.prompt_sha256) == 12
    assert result.issues == []


def test_extract_reads_level_and_paper_from_the_name_and_the_sidecar(write_pdf):
    pdf = write_pdf("2526_1st_S4MATH1.pdf")
    result = extractor(FakeGemini(level_text="中五")).extract(pdf)
    assert (result.document.level, result.document.level_source) == ("F4", "filename")
    assert result.document.level_text == "中五"           # kept for the mismatch check
    assert (result.document.paper.year, result.document.paper.term,
            result.document.paper.paper_number) == ("2025-26", "1st", 1)

    (pdf.parent / "2526_1st_S4MATH1.meta.txt").write_text("form: F6\nschool: ABC\n")
    result = extractor(FakeGemini()).extract(pdf)
    assert (result.document.level, result.document.level_source) == ("F6", "sidecar")
    assert result.document.paper.school == "ABC" and result.document.paper.source == "sidecar"


def test_the_pdf_bytes_are_read_once_and_handed_to_gemini(write_pdf):
    pdf = write_pdf("paper.pdf")
    gemini = FakeGemini()
    extractor(gemini).extract(pdf)
    path, prompt, schema, size = gemini.calls[0]
    assert prompt == "document_extractor_v1.txt" and schema == "QuestionExtractionPayload"
    assert size == pdf.stat().st_size


def test_a_gemini_can_be_injected():
    gemini = FakeGemini()
    assert DocumentExtractor(gemini=gemini).gemini is gemini
