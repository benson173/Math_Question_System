"""Render the diagram Gemini pointed at into a PNG.

When Gemini gives a usable box the image is cropped to it. When the box is
missing, malformed or implausibly small, the whole page is rendered instead -
a page image is still useful, an absent one is not.
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
from app.schemas import DiagramAsset, ExtractedDocument


def questions_needing_diagrams(document: ExtractedDocument) -> list:
    return [q for q in document.questions if q.diagram_required]


def render_diagrams(
    pdf_path: str | Path,
    document: ExtractedDocument,
    output_dir: str | Path,
    dpi: int = DEFAULT_DPI,
    padding: float = DEFAULT_PADDING,
) -> list[DiagramAsset]:
    """Render one PNG per question that needs a diagram.

    Raises ImportError with an actionable message if the optional rendering
    libraries are not installed.
    """
    wanted = questions_needing_diagrams(document)
    if not wanted:
        return []

    try:
        import pypdfium2
        from PIL import Image  # noqa: F401  (used via pypdfium2's to_pil)
    except ImportError as exc:
        raise ImportError(
            "Rendering diagrams needs pypdfium2 and Pillow. Install them with:\n"
            "    pip install pypdfium2 pillow"
        ) from exc

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    scale = dpi / PDF_POINTS_PER_INCH
    assets: list[DiagramAsset] = []
    pdf = pypdfium2.PdfDocument(str(pdf_path))

    try:
        for question in wanted:
            index = page_index_for(question, len(pdf))
            image = pdf[index].render(scale=scale).to_pil()

            region = question.diagram_region
            cropped = is_usable_region(region)
            if cropped:
                image = image.crop(crop_box(region, image.width, image.height, padding))

            name = f"{safe_asset_name(question.source_question_id)}.png"
            path = output_dir / name
            image.save(path)

            assets.append(DiagramAsset(
                source_question_id=question.source_question_id,
                page=index + 1,
                image_path=str(path),
                cropped=cropped,
                width=image.width,
                height=image.height,
            ))
    finally:
        pdf.close()

    return assets
