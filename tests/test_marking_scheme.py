"""A marking scheme joined to its paper by the printed question numbers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.extraction_validator import validate_extraction
from app.marking_scheme import (
    attach_marking_scheme,
    is_marking_scheme,
    marking_scheme_stem,
    pair_marking_schemes,
)
from app.pipeline import PdfIngestionPipeline
from app.schemas import (
    ExtractedDocument,
    ExtractedQuestion,
    ExtractionResult,
    MarkedAnswer,
    MarkingScheme,
    MarkingSchemePayload,
)
from scripts import attach_marking_scheme as attach_script
from scripts import ingest_pdfs as batch
from tests.test_batch_ingest import inbox  # noqa: F401  (fixture: isolated inbox dirs)
from tests.test_supabase_store import make_result


# --- naming -----------------------------------------------------------------

@pytest.mark.parametrize("name,stem", [
    ("S4-2024-mock-ms.pdf", "S4-2024-mock"),
    ("S4-2024-mock_MS.pdf", "S4-2024-mock"),
    ("2526_1st_S4MATH1-marking-scheme.pdf", "2526_1st_S4MATH1"),
    ("paper1 answers.pdf", "paper1"),
    ("paper1-solutions.pdf", "paper1"),
    ("mock-answer-key.pdf", "mock"),
])
def test_a_scheme_is_recognised_and_its_paper_named(name, stem):
    assert marking_scheme_stem(name) == stem
    assert is_marking_scheme(name)


@pytest.mark.parametrize("name", ["S4-2024-mock.pdf", "problems.pdf", "ms.pdf",
                                  "answers.pdf", "F4-mock-ms-notes.pdf"])
def test_a_paper_is_not_a_scheme(name):
    assert marking_scheme_stem(name) is None


def test_schemes_pair_with_papers_in_the_same_folder():
    files = [Path("in/S4-mock.pdf"), Path("in/S4-mock-ms.pdf"),
             Path("in/2024/dse.pdf"), Path("in/dse-ms.pdf"), Path("in/lonely-ms.pdf")]
    pairing = pair_marking_schemes(files)
    assert pairing.papers == [Path("in/S4-mock.pdf"), Path("in/2024/dse.pdf")]
    assert pairing.schemes == {Path("in/S4-mock.pdf"): Path("in/S4-mock-ms.pdf")}
    # dse-ms.pdf is in in/, dse.pdf in in/2024/: different folders, not a pair
    assert pairing.orphans == [Path("in/dse-ms.pdf"), Path("in/lonely-ms.pdf")]


def test_pairing_is_case_insensitive():
    pairing = pair_marking_schemes([Path("S4-Mock.pdf"), Path("s4-mock-MS.pdf")])
    assert pairing.schemes == {Path("S4-Mock.pdf"): Path("s4-mock-MS.pdf")}


# --- attaching --------------------------------------------------------------

def question(qid, text="求 x。", **kw):
    return ExtractedQuestion(source_question_id=qid, page_start=1, page_end=1,
                             question_text=text, **kw)


def document(*questions):
    return ExtractedDocument(level="F4", file_name="p.pdf", page_count=1,
                             questions=list(questions))


def scheme(*answers):
    return (MarkingSchemePayload(answers=list(answers)),
            MarkingScheme(file_name="p-ms.pdf", sha256="c" * 64, page_count=2))


def test_answers_land_on_the_matching_question():
    doc = document(question("1"), question("2(a)"))
    payload, record = scheme(
        MarkedAnswer(source_question_id="1", answer="x = 3", worked_solution="2x = 6"),
        MarkedAnswer(source_question_id="2(a)", answer="(1+15x)(1−15x)"),
    )
    report = attach_marking_scheme(doc, payload, record)

    assert doc.questions[0].answer == "x = 3"
    assert doc.questions[0].worked_solution == "2x = 6"
    assert doc.questions[1].answer == "(1+15x)(1−15x)"
    assert report.matched == ["1", "2(a)"]
    assert doc.marking_scheme.matched == ["1", "2(a)"]


def test_ids_match_despite_spacing_and_case():
    doc = document(question("18(a)(ii)"))
    payload, record = scheme(MarkedAnswer(source_question_id="18 (a) (II)", answer="7"))
    attach_marking_scheme(doc, payload, record)
    assert doc.questions[0].answer == "7"


def test_a_scheme_entry_with_no_question_is_reported_not_invented():
    doc = document(question("1"))
    payload, record = scheme(MarkedAnswer(source_question_id="9", answer="?"))
    report = attach_marking_scheme(doc, payload, record)
    assert report.unmatched_scheme_ids == ["9"]
    assert len(doc.questions) == 1


def test_the_scheme_wins_over_a_printed_answer_but_keeps_a_note():
    doc = document(question("1", answer="x = 4"))
    payload, record = scheme(MarkedAnswer(source_question_id="1", answer="x = 3"))
    report = attach_marking_scheme(doc, payload, record)
    assert doc.questions[0].answer == "x = 3"
    assert "x = 4" in doc.questions[0].extraction_notes[0]
    assert report.answer_conflicts == ["1"]


def test_the_same_answer_twice_is_no_conflict():
    doc = document(question("1", answer="x = 3"))
    payload, record = scheme(MarkedAnswer(source_question_id="1", answer="x = 3 "))
    report = attach_marking_scheme(doc, payload, record)
    assert report.answer_conflicts == [] and doc.questions[0].extraction_notes == []


def test_marks_fill_only_where_the_paper_printed_none():
    doc = document(question("1"), question("2", marks=5),
                   question("3(a)", group_marks=4, group_marks_scope="3"))
    payload, record = scheme(
        MarkedAnswer(source_question_id="1", answer="a", marks=3),
        MarkedAnswer(source_question_id="2", answer="b", marks=99),
        MarkedAnswer(source_question_id="3(a)", answer="c", marks=2),
    )
    report = attach_marking_scheme(doc, payload, record)
    assert doc.questions[0].marks == 3
    assert doc.questions[1].marks == 5           # the paper's own mark stands
    assert doc.questions[2].marks is None        # a group total is never split
    assert report.marks_filled == ["1"]


def test_questions_the_scheme_did_not_cover_are_listed():
    doc = document(question("1"), question("2"))
    payload, record = scheme(MarkedAnswer(source_question_id="1", answer="a"))
    report = attach_marking_scheme(doc, payload, record)
    assert report.questions_without_answer == ["2"]


def test_scheme_notes_are_kept_and_labelled():
    doc = document(question("1"))
    payload, record = scheme(MarkedAnswer(source_question_id="1", answer="a",
                                          extraction_notes=["two methods printed"]))
    attach_marking_scheme(doc, payload, record)
    assert doc.questions[0].extraction_notes == ["Marking scheme: two methods printed"]


# --- what the validator says ------------------------------------------------

def codes(doc):
    return sorted(i.issue_code for i in validate_extraction(doc))


def test_a_scheme_that_fits_is_no_issue():
    doc = document(question("1"))
    payload, record = scheme(MarkedAnswer(source_question_id="1", answer="a"))
    attach_marking_scheme(doc, payload, record)
    assert codes(doc) == []


def test_unmatched_entries_and_uncovered_questions_are_low():
    doc = document(question("1"), question("2"))
    payload, record = scheme(MarkedAnswer(source_question_id="1", answer="a"),
                             MarkedAnswer(source_question_id="7", answer="b"))
    attach_marking_scheme(doc, payload, record)
    issues = {i.issue_code: i.severity for i in validate_extraction(doc)}
    assert issues == {"MARKING_SCHEME_UNMATCHED": "low", "ANSWER_NOT_IN_MARKING_SCHEME": "low"}


def test_a_scheme_that_matches_nothing_is_medium():
    doc = document(question("1"))
    payload, record = scheme(MarkedAnswer(source_question_id="9", answer="b"))
    attach_marking_scheme(doc, payload, record)
    assert "MARKING_SCHEME_UNUSED" in codes(doc)


def test_no_scheme_means_no_scheme_issues():
    assert codes(document(question("1"))) == []


# --- through the pipeline ---------------------------------------------------

class FakeSchemeExtractor:
    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def extract(self, path):
        self.calls.append(Path(path))
        return (MarkingSchemePayload(answers=self.answers),
                MarkingScheme(file_name=Path(path).name, sha256="d" * 64, page_count=1))


class FakeExtractor:
    def __init__(self, result):
        self.result = result

    def extract(self, pdf_path):
        return self.result


class Settings:
    render_diagrams = False
    render_tables = False
    repair_extraction = True
    extraction_version = "QEE_v1"
    question_object_version = "QOS_v1"
    gemini_extractor_model = "m"
    diagram_dpi = 200


class RecordingRepository:
    def __init__(self):
        self.saved = []

    def save_extraction_result(self, result):
        self.saved.append(result)


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr("app.json_exporter.EXTRACTED_DIR", tmp_path / "extracted")
    monkeypatch.setattr("app.json_exporter.HISTORY_DIR", tmp_path / "history")
    monkeypatch.setattr("app.json_exporter.DIAGRAMS_DIR", tmp_path / "diagrams")
    return tmp_path


def test_a_scheme_beside_the_paper_is_attached_during_ingestion(isolated):
    schemes = FakeSchemeExtractor([MarkedAnswer(source_question_id="1", answer="x = 3")])
    pipeline = PdfIngestionPipeline(extractor=FakeExtractor(make_result()),
                                    repository=RecordingRepository(), settings=Settings(),
                                    marking_scheme_extractor=schemes)
    result = pipeline.run_one_pdf("p.pdf", marking_scheme_path="p-ms.pdf")

    assert schemes.calls == [Path("p-ms.pdf")]
    assert result.document.questions[0].answer == "x = 3"
    assert result.document.marking_scheme.file_name == "p-ms.pdf"
    assert any("answers attached from p-ms.pdf" in r for r in result.repairs)


def test_without_a_scheme_the_extractor_is_never_built(isolated):
    pipeline = PdfIngestionPipeline(extractor=FakeExtractor(make_result()),
                                    repository=RecordingRepository(), settings=Settings())
    pipeline.run_one_pdf("p.pdf")
    assert pipeline._marking_scheme_extractor is None


def test_attaching_later_is_a_new_run_of_the_same_paper(isolated):
    earlier = make_result(run_id="run-first")
    schemes = FakeSchemeExtractor([MarkedAnswer(source_question_id="2(a)", answer="7")])
    repository = RecordingRepository()
    pipeline = PdfIngestionPipeline(extractor=FakeExtractor(earlier), repository=repository,
                                    settings=Settings(), marking_scheme_extractor=schemes)

    result = pipeline.attach_marking_scheme(earlier, "p-ms.pdf")

    assert result.run.run_id != "run-first"
    assert result.run.model == "m" and result.run.extraction_version == "QEE_v1"
    assert result.document.questions[1].answer == "7"
    assert repository.saved == [result]
    # same paper, same JSON path; history keeps both runs
    history = sorted((isolated / "history").rglob("*.json"))
    assert [p.stem for p in history] == [result.run.run_id]


# --- the standalone script and the batch ------------------------------------

def test_the_script_finds_the_paper_by_the_scheme_name(tmp_path, monkeypatch):
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    (extracted / "S4-mock-aaaaaaaaaaaa.json").write_text("{}")
    (extracted / "other-bbbbbbbbbbbb.json").write_text("{}")
    monkeypatch.setattr(attach_script, "EXTRACTED_DIR", extracted)

    assert attach_script.find_extraction_for(Path("S4-mock-ms.pdf")).name == \
        "S4-mock-aaaaaaaaaaaa.json"
    assert attach_script.find_extraction_for(Path("nobody-ms.pdf")) is None
    assert attach_script.find_extraction_for(Path("S4-mock.pdf")) is None


def test_the_batch_hands_a_paired_scheme_to_the_pipeline(inbox, monkeypatch):
    calls = []

    class FakePipeline:
        def __init__(self, *a, **k):
            pass

        def run_one_pdf(self, path, marking_scheme_path=None):
            calls.append((path.name, marking_scheme_path and marking_scheme_path.name))
            doc = ExtractedDocument(level="F4", file_name=path.name, page_count=1,
                                    questions=[question("1")])
            return ExtractionResult(document=doc)

    class FakeRepository:
        def __init__(self, verbose=True): pass
        def describe_target(self): return "test"

    monkeypatch.setattr(batch, "PdfIngestionPipeline", FakePipeline)
    monkeypatch.setattr(batch, "Repository", FakeRepository)
    (inbox["inbox"] / "S4-mock.pdf").write_bytes(b"AAA")
    (inbox["inbox"] / "S4-mock-ms.pdf").write_bytes(b"BBB")

    batch.main([])
    assert calls == [("S4-mock.pdf", "S4-mock-ms.pdf")]
    assert {p.name for p in inbox["processed"].iterdir()} == {"S4-mock.pdf", "S4-mock-ms.pdf"}


def test_the_batch_attaches_an_orphan_scheme_to_the_paper_done_earlier(inbox, monkeypatch, tmp_path):
    attached = []

    class FakePipeline:
        def __init__(self, *a, **k):
            pass

        def attach_marking_scheme(self, result, scheme_path):
            attached.append((result.document.file_name, scheme_path.name))
            result.document.marking_scheme = MarkingScheme(
                file_name=scheme_path.name, sha256="e" * 64, page_count=1, matched=["1"])
            return result

    class FakeRepository:
        def __init__(self, verbose=True): pass
        def describe_target(self): return "test"

    monkeypatch.setattr(batch, "PdfIngestionPipeline", FakePipeline)
    monkeypatch.setattr(batch, "Repository", FakeRepository)
    monkeypatch.setattr(attach_script, "EXTRACTED_DIR", inbox["extracted"])

    from app.json_exporter import export_extraction_json
    earlier = make_result()
    earlier.document.file_name = "S4-mock.pdf"
    export_extraction_json(earlier, inbox["extracted"] / "S4-mock-aaaaaaaaaaaa.json")
    (inbox["inbox"] / "S4-mock-ms.pdf").write_bytes(b"BBB")

    assert batch.main([]) == 0
    assert attached == [("S4-mock.pdf", "S4-mock-ms.pdf")]
    assert (inbox["processed"] / "S4-mock-ms.pdf").exists()


def test_an_orphan_scheme_with_no_paper_stays_in_the_inbox(inbox, monkeypatch, capsys):
    class FakePipeline:
        def __init__(self, *a, **k): pass

    class FakeRepository:
        def __init__(self, verbose=True): pass
        def describe_target(self): return "test"

    monkeypatch.setattr(batch, "PdfIngestionPipeline", FakePipeline)
    monkeypatch.setattr(batch, "Repository", FakeRepository)
    monkeypatch.setattr(attach_script, "EXTRACTED_DIR", inbox["extracted"])
    (inbox["inbox"] / "nobody-ms.pdf").write_bytes(b"BBB")

    batch.main([])
    assert (inbox["inbox"] / "nobody-ms.pdf").exists()
    assert "put the paper in the inbox too" in capsys.readouterr().out


# --- the rows -------------------------------------------------------------------

def test_answer_source_tells_a_scheme_answer_from_a_printed_one():
    from app.supabase_store import question_rows, run_row
    result = make_result()
    result.document.questions[0].answer = "printed"
    payload, record = scheme(MarkedAnswer(source_question_id="2(a)", answer="from ms"))
    attach_marking_scheme(result.document, payload, record)

    rows = question_rows(result, "d", "r")
    assert rows[0]["answer_source"] == "paper"
    assert rows[1]["answer_source"] == "marking_scheme"
    assert run_row(result, "d")["marking_scheme_file_name"] == "p-ms.pdf"
