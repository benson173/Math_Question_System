"""The crop arithmetic, tested without any imaging library."""

from __future__ import annotations

import pytest

from app.diagram_geometry import (
    MIN_REGION_FRACTION,
    crop_box,
    is_usable_region,
    page_index_for,
    safe_asset_name,
)
from app.schemas import DiagramRegion, ExtractedQuestion, REGION_SCALE


def region(y_min=200, x_min=100, y_max=600, x_max=900, page=1) -> DiagramRegion:
    return DiagramRegion(page=page, y_min=y_min, x_min=x_min, y_max=y_max, x_max=x_max)


def question(**overrides) -> ExtractedQuestion:
    defaults = dict(
        source_question_id="16",
        page_start=8,
        page_end=8,
        question_text="圖中，O 是 △ABC 的外心。",
        diagram_required=True,
    )
    defaults.update(overrides)
    return ExtractedQuestion(**defaults)


# --- filename safety --------------------------------------------------------

@pytest.mark.parametrize("question_id, expected", [
    ("16", "16"),
    ("17(a)", "17-a"),
    ("1(a)(i)", "1-a-i"),
    ("2 (b)", "2-b"),
    ("../../etc/passwd", "etc-passwd"),
    ("", "question"),
    ("()", "question"),
])
def test_safe_asset_name(question_id, expected):
    assert safe_asset_name(question_id) == expected


def test_safe_asset_name_never_escapes_its_directory():
    for question_id in ("../x", "a/b", "..", "a\\b"):
        name = safe_asset_name(question_id)
        assert "/" not in name and "\\" not in name and ".." not in name


# --- region validity --------------------------------------------------------

def test_a_normal_region_is_usable():
    assert is_usable_region(region()) is True


def test_missing_region_is_not_usable():
    assert is_usable_region(None) is False


@pytest.mark.parametrize("kwargs", [
    dict(x_min=900, x_max=100),        # inverted
    dict(y_min=600, y_max=200),        # inverted
    dict(x_min=-10),                   # off page
    dict(x_max=REGION_SCALE + 1),      # off page
    dict(x_min=500, x_max=500),        # zero width
])
def test_malformed_regions_are_rejected(kwargs):
    assert is_usable_region(region(**kwargs)) is False


def test_a_sliver_is_rejected_as_a_mis_detection():
    sliver = int(MIN_REGION_FRACTION * REGION_SCALE) - 1
    assert is_usable_region(region(x_min=100, x_max=100 + sliver)) is False


def test_a_box_at_the_minimum_size_is_accepted():
    minimum = int(MIN_REGION_FRACTION * REGION_SCALE)
    assert is_usable_region(region(x_min=100, x_max=100 + minimum,
                                   y_min=100, y_max=100 + minimum)) is True


# --- crop arithmetic --------------------------------------------------------

def test_crop_box_maps_the_region_onto_pixels():
    # Half the width, half the height, no padding.
    box = crop_box(region(y_min=0, x_min=0, y_max=500, x_max=500),
                   image_width=1000, image_height=1000, padding=0)
    assert box == (0, 0, 500, 500)


def test_crop_box_respects_the_1000_scale_independently_of_image_size():
    box = crop_box(region(y_min=250, x_min=250, y_max=750, x_max=750),
                   image_width=800, image_height=400, padding=0)
    assert box == (200, 100, 600, 300)


def test_padding_widens_the_box():
    plain = crop_box(region(), 1000, 1000, padding=0)
    padded = crop_box(region(), 1000, 1000, padding=0.05)
    assert padded[0] < plain[0] and padded[1] < plain[1]
    assert padded[2] > plain[2] and padded[3] > plain[3]


def test_padding_is_clamped_to_the_image():
    box = crop_box(region(y_min=0, x_min=0, y_max=1000, x_max=1000),
                   image_width=600, image_height=800, padding=0.5)
    assert box == (0, 0, 600, 800)


def test_crop_box_is_never_empty():
    left, top, right, bottom = crop_box(
        region(y_min=999, x_min=999, y_max=1000, x_max=1000),
        image_width=100, image_height=100, padding=0)
    assert right > left and bottom > top


def test_crop_box_stays_inside_the_image():
    for width, height in [(100, 100), (2480, 3508), (37, 991)]:
        left, top, right, bottom = crop_box(region(), width, height, padding=0.2)
        assert 0 <= left < right <= width
        assert 0 <= top < bottom <= height


# --- page selection ---------------------------------------------------------

def test_page_comes_from_the_region_when_present():
    q = question(page_start=8, diagram_region=region(page=3))
    assert page_index_for(q, page_count=9) == 2


def test_page_falls_back_to_the_question_when_region_is_missing():
    assert page_index_for(question(page_start=8, diagram_region=None), 9) == 7


def test_page_falls_back_when_the_region_page_is_zero():
    q = question(page_start=8, diagram_region=region(page=0))
    assert page_index_for(q, page_count=9) == 7


def test_page_is_clamped_into_the_document():
    assert page_index_for(question(diagram_region=region(page=99)), page_count=9) == 8
    assert page_index_for(question(page_start=-4, diagram_region=None), page_count=9) == 0
