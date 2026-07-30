import pytest

from ClipAI.core.models import DisplayMetrics
from ClipAI.ui.popup_layout import PopupLayoutPolicy


@pytest.mark.parametrize("scale", [1.0, 1.25, 1.5, 1.75, 2.0])
def test_popup_layout_scales_logical_defaults_and_stays_in_work_area(scale: float) -> None:
    metrics = DisplayMetrics(scale, 100, 50, 1920, 1080, 1800, 1000)
    bounds = PopupLayoutPolicy().calculate(metrics)
    assert bounds.width == min(400, int(1920 / scale * 0.60))
    assert bounds.height == min(320, int(1080 / scale * 0.70))
    assert bounds.x >= 100 + int(16 * scale)
    assert bounds.y >= 50 + int(16 * scale)
    assert bounds.x + int(bounds.width * scale) <= 100 + 1920 - int(16 * scale)
    assert bounds.y + int(bounds.height * scale) <= 50 + 1080 - int(16 * scale)


def test_popup_layout_keeps_stable_height_for_short_and_long_content() -> None:
    metrics = DisplayMetrics(1.0, 0, 0, 1920, 1080, 500, 400)
    policy = PopupLayoutPolicy()
    assert policy.calculate(metrics, content_lines=4).height == 320
    assert policy.calculate(metrics, content_lines=10).height == 320
    assert policy.calculate(metrics, content_lines=30).height == 320


def test_comfortable_physical_size_matches_reference_displays() -> None:
    policy = PopupLayoutPolicy()
    desktop = policy.calculate(DisplayMetrics(1.25, 0, 0, 2560, 1440, 1280, 720))
    laptop = policy.calculate(DisplayMetrics(2.0, 0, 0, 2880, 1920, 1440, 960))
    assert (round(desktop.width * 1.25), round(desktop.height * 1.25)) == (500, 400)
    assert (round(laptop.width * 2.0), round(laptop.height * 2.0)) == (800, 640)


def test_popup_layout_clamps_to_small_work_area() -> None:
    bounds = PopupLayoutPolicy().calculate(DisplayMetrics(2.0, 0, 0, 800, 600, 400, 300))
    assert bounds.width <= 480
    assert bounds.height <= 420
