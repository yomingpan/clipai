import pytest

from ClipAI.core.models import DisplayMetrics, PopupBounds
from ClipAI.ui.popup_layout import PopupLayoutPolicy, popup_bounds_from_tk_geometry


def test_tk_geometry_preserves_logical_size_and_physical_position() -> None:
    assert popup_bounds_from_tk_geometry("440x330-120+95") == PopupBounds(
        -120,
        95,
        440,
        330,
    )


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


@pytest.mark.parametrize("scale", [1.0, 1.25, 1.5, 2.0])
@pytest.mark.parametrize("work_x", [-1920, 0, 1920])
def test_default_bottom_center_uses_monitor_work_area_and_physical_size(scale, work_x) -> None:
    metrics = DisplayMetrics(scale, work_x, 50, 1920, 1040, work_x + 200, 200)
    bounds = PopupLayoutPolicy().calculate(metrics)
    assert bounds.x == work_x + (1920 - int(bounds.width * scale)) // 2
    assert bounds.y == 50 + 1040 - int(bounds.height * scale) - int(16 * scale)
    assert PopupLayoutPolicy().calculate(
        DisplayMetrics(scale, work_x, 50, 1920, 1040, work_x + 1500, 800)
    ) == bounds


def test_saved_placement_switch_changes_next_layout_and_retains_cursor_clamping() -> None:
    placement = "bottom_center"
    policy = PopupLayoutPolicy(lambda: placement)
    metrics = DisplayMetrics(1.5, -1920, 50, 1920, 1040, -1000, 400)
    bottom = policy.calculate(metrics)
    placement = "cursor"
    cursor = policy.calculate(metrics)
    assert (cursor.x, cursor.y) == (-1200, 280)
    assert cursor != bottom
    edge = policy.calculate(DisplayMetrics(1.5, -1920, 50, 1920, 1040, -10, 1080))
    assert edge.x + int(edge.width * 1.5) == -24
    assert edge.y + int(edge.height * 1.5) == 1066
