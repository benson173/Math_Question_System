"""Every script's main() runs end to end on a saved extraction, with Gemini faked."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import analyzer as analyzer_module
from app.analyzer import (RpdiceAnalyzer, analysis_history_path, analysis_output_path,
                          export_analysis_json)
from app.json_exporter import export_extraction_json, history_output_path
from app.marking_scheme import MarkingSchemeExtractor
from app.rpdice import AnalysisPayload
from app.schemas import MarkedAnswer, MarkingSchemePayload
from app.taxonomy import load_taxonomy
from scripts import analyse_extractions, analyse_rpdice, check_taxonomy, export_markdown
from scripts import score_rpdice, show_extraction
from tests.test_rpdice import analysis, make_analysis_result
from tests.test_supabase_store import make_result


@pytest.fixture
def extracted(tmp_path, monkeypatch):
    """A folder holding one saved extraction, wired as data/extracted."""
    folder = tmp_path / "extracted"
    folder.mkdir()
    result = make_result()
    result.document.questions[1].depends_on = ["1"]
    export_extraction_json(result, folder / "p-aaaaaaaaaaaa.json")
    for module in (show_extraction, export_markdown, analyse_extractions, analyse_rpdice):
        monkeypatch.setattr(module, "EXTRACTED_DIR", folder)
    return folder


# --- the two Gemini-facing classes, against fakes ---------------------------

class FakeGemini:
    last_usage = {"input_tokens": 50, "output_tokens": 20}

    def __init__(self, payload):
        self.payload, self.prompts = payload, []

    def generate_json(self, prompt, schema):
        self.prompts.append(prompt)
        assert schema is AnalysisPayload
        return self.payload

    def extract_pdf_json(self, pdf_path, prompt_path, schema, pdf_bytes=None):
        assert schema is MarkingSchemePayload
        return self.payload


class Settings:
    gemini_extractor_model = "m"


def test_the_analyzer_runs_end_to_end_against_a_fake_gemini():
    payload = AnalysisPayload(analyses=[analysis(qid="1"), analysis(qid="2(a)",
                                                                      difficulty_drivers=["C"])])
    gemini = FakeGemini(payload)
    built = RpdiceAnalyzer.__new__(RpdiceAnalyzer)
    built.gemini, built.taxonomy, built.settings = gemini, load_taxonomy(), Settings()

    result = built.analyse(make_result())

    assert "na.factor.dos |" in gemini.prompts[0]                 # the taxonomy went along
    assert result.run.input_tokens == 50 and len(result.run.prompt_sha256) == 12
    assert result.analyses[1].difficulty_drivers == ["R", "E"]    # repaired, not argued
    assert result.issues == []
    assert set(result.by_key()) == {"aaaaaaaaaaaa:1", "aaaaaaaaaaaa:2(a)"}


def test_the_marking_scheme_extractor_reads_the_pdf_once(write_pdf):
    pdf = write_pdf("S4-mock-ms.pdf", pages=2)
    built = MarkingSchemeExtractor.__new__(MarkingSchemeExtractor)
    built.gemini = FakeGemini(MarkingSchemePayload(answers=[
        MarkedAnswer(source_question_id="1", answer="x = 3")]))
    payload, record = built.extract(pdf)
    assert payload.answers[0].answer == "x = 3"
    assert record.file_name == "S4-mock-ms.pdf" and record.page_count == 2
    assert len(record.sha256) == 64


def test_analysis_and_history_paths_line_up(monkeypatch, tmp_path):
    monkeypatch.setattr(analyzer_module, "ANALYSES_DIR", tmp_path)
    result = make_analysis_result()
    assert analysis_output_path(result) == tmp_path / "p-aaaaaaaaaaaa.json"
    assert analysis_history_path(result) == tmp_path / "history" / "p-aaaaaaaaaaaa" / "an1.json"
    assert history_output_path(make_result()).name == "run1.json"


# --- scripts ----------------------------------------------------------------

def test_show_extraction_prints_dependencies(extracted, capsys):
    assert show_extraction.main([]) == 0
    out = capsys.readouterr().out
    assert "2(a)" in out and "depends on 1" in out
    assert "Level  : F4" in out


def test_show_extraction_takes_a_file_even_when_the_folder_is_empty(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(show_extraction, "EXTRACTED_DIR", tmp_path / "empty")
    path = export_extraction_json(make_result(), tmp_path / "x.json")
    assert show_extraction.main(["--file", str(path), "2"]) == 0
    assert "2(a)" in capsys.readouterr().out


def test_export_markdown_rebuilds_the_report(extracted, capsys):
    assert export_markdown.main([]) == 0
    report = extracted / "p-aaaaaaaaaaaa.md"
    assert report.exists() and "depends on 1" in report.read_text(encoding="utf-8")


def test_analyse_extractions_writes_a_cross_paper_report(extracted, capsys):
    assert analyse_extractions.main([]) == 0
    assert list(extracted.glob("analysis-*.md"))
    assert "By paper" in capsys.readouterr().out


def test_check_taxonomy_reports_ok(capsys):
    assert check_taxonomy.main() == 0
    assert "Taxonomy OK" in capsys.readouterr().out


def test_score_rpdice_check_validates_the_gold_file(capsys):
    assert score_rpdice.main(["--check"]) == 0
    assert "Golden set OK" in capsys.readouterr().out


def test_score_rpdice_scores_a_saved_analysis(tmp_path, monkeypatch, capsys):
    from app.paths import RPDICE_GOLD_CSV
    from app.rpdice import read_gold
    monkeypatch.setattr(score_rpdice, "ANALYSES_DIR", tmp_path)
    gold = read_gold(RPDICE_GOLD_CSV)[0]
    result = make_analysis_result(sha256=gold.question_key.split(":")[0] + "0" * 52,
                                  analyses=[analysis(qid=gold.source_question_id,
                                                     skills=gold.skills, errors=gold.errors,
                                                     levels=gold.levels)])
    export_analysis_json(result, tmp_path / "a.json")

    assert score_rpdice.main([]) == 0
    out = capsys.readouterr().out
    assert "Compared 1 questions" in out and "| R Recognition | 100% |" in out
    assert list(tmp_path.glob("score-*.md"))


def test_analyse_rpdice_runs_the_analyzer_over_the_folder(extracted, tmp_path, monkeypatch, capsys):
    class FakeAnalyzer:
        taxonomy = load_taxonomy()

        def analyse(self, result):
            return make_analysis_result(file_name=result.document.file_name,
                                        sha256=result.source.sha256)

    monkeypatch.setattr(analyse_rpdice, "RpdiceAnalyzer", FakeAnalyzer)
    monkeypatch.setattr(analyse_rpdice, "_client", lambda: None)
    monkeypatch.setattr(analyzer_module, "ANALYSES_DIR", tmp_path / "analyses")

    assert analyse_rpdice.main([]) == 0
    written = list((tmp_path / "analyses").glob("*.json"))
    assert len(written) == 1
    assert json.loads(written[0].read_text())["analyses"][0]["source_question_id"] == "1"
    assert (tmp_path / "analyses" / "history").exists()
    assert "2 analysed" in capsys.readouterr().out
