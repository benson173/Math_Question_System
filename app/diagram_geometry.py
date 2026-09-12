"""Pure geometry for cropping a region of a page.

Separate from the renderer so the arithmetic can be tested without any imaging
library, and so the validator can reuse the region check without pulling in the
rendering stack.
"""

from __future__ import annotations

import re

from app.schemas import PageRegion, REGION_SCALE


# A box smaller than this fraction of the page in either direction is treated as
# a mis-detection rather than a diagram.
MIN_REGION_FRACTION = 0.02

# Breathing room added around the crop, as a fraction of the page.
DEFAULT_PADDING = 0.02

DEFAULT_DPI = 200
PDF_POINTS_PER_INCH = 72.0


def safe_asset_name(source_question_id: str) -> str:
    """A filename-safe version of a question id: "17(a)(i)" -> "17-a-i"."""
    cleaned = re.sub(r"[^0-9A-Za-z]+", "-", source_question_id).strip("-")
    return cleaned or "question"


def is_usable_region(region: PageRegion | None) -> bool:
    """True if the box is inside the page and big enough to be a diagram."""
    if region is None:
        return False

    values = (region.y_min, region.x_min, region.y_max, region.x_max)
    if any(v < 0 or v > REGION_SCALE for v in values):
        return False
    if region.x_min >= region.x_max or region.y_min >= region.y_max:
        return False

    minimum = MIN_REGION_FRACTION * REGION_SCALE
    return (region.x_max - region.x_min) >= minimum and \
           (region.y_max - region.y_min) >= minimum


def crop_box(
    region: PageRegion,
    image_width: int,
    image_height: int,
    padding: float = DEFAULT_PADDING,
) -> tuple[int, int, int, int]:
    """Convert a 0-1000 region into pixel (left, top, right, bottom).

    Padding widens the box by a fraction of the page; the result is clamped to
    the image so a box near an edge cannot run off it.
    """
    pad_x = padding * image_width
    pad_y = padding * image_height

    left = region.x_min / REGION_SCALE * image_width - pad_x
    right = region.x_max / REGION_SCALE * image_width + pad_x
    top = region.y_min / REGION_SCALE * image_height - pad_y
    bottom = region.y_max / REGION_SCALE * image_height + pad_y

    left = max(0, int(round(left)))
    top = max(0, int(round(top)))
    right = min(image_width, int(round(right)))
    bottom = min(image_height, int(round(bottom)))

    # Never return an empty box, whatever the rounding did.
    right = max(right, left + 1)
    bottom = max(bottom, top + 1)
    return left, top, right, bottom


def page_index_for(question, page_count: int, region=None) -> int:
    """0-based page to render, clamped into the document.

    Prefers the page the region names, falls back to where the question starts.
    Passing `region` explicitly lets a table use its own box rather than the
    question's diagram.
    """
    if region is None:
        region = question.diagram_region
    page = region.page if region is not None and region.page > 0 else question.page_start
    page = max(1, min(page, page_count))
    return page - 1
