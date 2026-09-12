"""What a PDF may be called, and what its name turns into.

The PDF's own name becomes part of the output JSON name, the diagram folder
name and every image link in the report, so a name with a space or a bracket
used to end the Markdown link early and the images did not render.
"""

from __future__ import annotations

import pytest

from app.json_exporter import diagram_output_dir, extraction_output_path
from app.markdown_exporter import render_markdown
from app.paths import MAX_STEM_LENGTH, safe_stem
from app.schemas import (
    ExtractedDocument,
    ExtractedQuestion,
    ExtractionResult,
    ExtractionRun,
    RenderedImage,
    SourceDocument,
)


def result_for(file_name: str) -> ExtractionResult:
    document = ExtractedDocument(level="F4", file_name=file_name, page_count=1, questions=[
        ExtractedQuestion(source_question_id="16", page_start=1, page_end=1,
                          question_text="圖中…", diagram_required=True)])
    return ExtractionResult(
        document=document, issues=[],
        source=SourceDocument(file_name=file_name, sha256="abc123def456" + "0" * 52,
                              page_count=1, byte_size=1),
        run=ExtractionRun(run_id="r", extracted_at="t", extraction_version="v",
                          question_object_version="v", model="m"),
    )


def image_link(file_name: str) -> str:
    result = result_for(file_name)
    json_path = extraction_output_path(result)
    result.diagrams = [RenderedImage(
        source_question_id="16", kind="diagram", index=0, page=1,
        image_path=str(diagram_output_dir(result) / "16.png"),
        cropped=True, width=1, height=1)]
    markdown = render_markdown(result, json_path.with_suffix(".md"))
    line = next(l for l in markdown.splitlines() if l.startswith("![16]"))
    return line[line.index("(") + 1:line.rindex(")")]


# --- the stem ---------------------------------------------------------------

@pytest.mark.parametrize("name, expected", [
    ("sample.pdf", "sample"),
    ("2024_mock_paper1.pdf", "2024_mock_paper1"),
    ("paper-1.pdf", "paper-1"),
    ("數學卷一.pdf", "數學卷一"),              # letters in any script are kept
    ("Mock Paper 1.pdf", "Mock-Paper-1"),      # spaces become hyphens
    ("Paper (2).pdf", "Paper-2"),              # brackets dropped
    ("P6 卷 [A].pdf", "P6-卷-A"),
    ("a/b.pdf", "b"),                          # Path().stem takes the last part
    ("  padded  .pdf", "padded"),
    ("....pdf", "document"),                   # nothing usable left
    ("", "document"),
])
def test_safe_stem(name, expected):
    assert safe_stem(name) == expected


def test_a_very_long_name_is_capped():
    assert len(safe_stem("a" * 300 + ".pdf")) == MAX_STEM_LENGTH


def test_the_stem_never_contains_a_path_separator():
    for name in ("a/b.pdf", "a\\b.pdf", "../../etc/passwd.pdf"):
        stem = safe_stem(name)
        assert "/" not in stem and "\\" not in stem and ".." not in stem


# --- links in the report ----------------------------------------------------

@pytest.mark.parametrize("file_name", [
    "sample.pdf",
    "Mock Paper 1.pdf",
    "Paper (2).pdf",
    "P6 卷 [A].pdf",
    "DSE 2024 — Paper 1 (Final).pdf",
    "數學卷一.pdf",
])
def test_an_image_link_never_breaks(file_name):
    link = image_link(file_name)
    # A space or bracket would close the Markdown link early.
    for character in (" ", "(", ")", "[", "]"):
        assert character not in link


def test_a_non_ascii_name_is_percent_encoded_in_the_link():
    assert "%E6%95%B8" in image_link("數學卷一.pdf")


def test_the_folder_itself_stays_readable():
    # Encoding belongs in the link, not on disk.
    assert "數學卷一" in str(diagram_output_dir(result_for("數學卷一.pdf")))


# --- names that differ only by punctuation ----------------------------------

def test_content_still_decides_the_output_name():
    # Two different names, same content - the hash half matches, so a rename
    # cannot hide that these are the same paper.
    a = extraction_output_path(result_for("Mock Paper 1.pdf")).name
    b = extraction_output_path(result_for("mock-paper-1.pdf")).name
    assert a.endswith("-abc123def456.json") and b.endswith("-abc123def456.json")
