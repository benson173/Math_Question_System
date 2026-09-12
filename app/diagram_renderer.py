"""Render the regions Gemini pointed at into PNGs.

Two kinds of image come out of a page: the diagram a question cannot be
answered without, and a picture of each printed table. The table is also
transcribed as Markdown in question_text - the text is what later stages
compute with, the image is the record of what the page actually looked like,
which matters most exactly where Markdown falls short (merged cells, two-level
headers, tables printed side by side).

When a box is usable the image is cropped to it. When it is missing, malformed
or implausibly small, the whole page is rendered instead - a page image is
still usable, an absent one is not.
"""

from __future__ import annotations

from pathlib import Path

from app.diagram_geometry import (
    DEFAULT_DPI,
    DEFAULT_PADDING,
    PDF_POINTS_PER_INCH,
    crop_box,
    is_usable_region,
    page_index_for,
    safe_asset_name,
)
from app.schemas import ExtractedDocument, PageRegion, RenderedImage


def asset_file_name(source_question_id: str, kind: str, index: int) -> str:
    """A diagram is named for its question; tables are numbered after it."""
    stem = safe_asset_name(source_question_id)
    return f"{stem}.png" if kind == "diagram" else f"{stem}-table-{index + 1}.png"


def planned_images(document: ExtractedDocument) -> list[tuple]:
    """Every (question, kind, index, region) this document needs rendered."""
    planned = []
    for question in document.questions:
        if question.diagram_required:
            planned.append((question, "diagram", 0, question.diagram_region))
        for index, region in enumerate(question.table_regions):
            planned.append((question, "table", index, region))
    return planned


def render_question_images(
    pdf_path: str | Path,
    document: ExtractedDocument,
    output_dir: str | Path,
    dpi: int = DEFAULT_DPI,
    padding: float = DEFAULT_PADDING,
    kinds: tuple[str, ...] = ("diagram", "table"),
) -> list[RenderedImage]:
    """Render one PNG per diagram and per table.

    Raises ImportError with an actionable message if the optional rendering
    libraries are not installed.
    """
    wanted = [item for item in planned_images(document) if item[1] in kinds]
    if not wanted:
        return []

    try:
        import pypdfium2
        from PIL import Image  # noqa: F401  (used via pypdfium2's to_pil)
    except ImportError as exc:
        raise ImportError(
            "Rendering images needs pypdfium2 and Pillow. Install them with:\n"
            "    pip install pypdfium2 pillow"
        ) from exc

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    scale = dpi / PDF_POINTS_PER_INCH
    assets: list[RenderedImage] = []
    pdf = pypdfium2.PdfDocument(str(pdf_path))

    # One render per page, reused by every region on it: a question with a
    # diagram and two tables would otherwise rasterise the same page three
    # times.
    pages: dict[int, object] = {}

    try:
        for question, kind, index, region in wanted:
            page_index = page_index_for(question, len(pdf), region)
            if page_index not in pages:
                pages[page_index] = pdf[page_index].render(scale=scale).to_pil()
            page_image = pages[page_index]

            cropped = is_usable_region(region)
            image = (page_image.crop(
                        crop_box(region, page_image.width, page_image.height, padding))
                     if cropped else page_image)

            path = output_dir / asset_file_name(question.source_question_id, kind, index)
            image.save(path)

            assets.append(RenderedImage(
                source_question_id=question.source_question_id,
                kind=kind,
                index=index,
                page=page_index + 1,
                image_path=str(path),
                cropped=cropped,
                width=image.width,
                height=image.height,
            ))
    finally:
        pdf.close()

    return assets
