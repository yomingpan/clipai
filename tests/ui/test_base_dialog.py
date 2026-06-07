from __future__ import annotations

import pytest

from ClipAI.ui.base_dialog import (
    RoundedSurfacePainter,
    SurfaceFlashController,
    SurfaceStateColors,
    rgb_to_hex,
)


class FakeCanvas:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []

    def delete(self, *args, **kwargs) -> None:
        self.calls.append(("delete", args, kwargs))

    def create_rectangle(self, *args, **kwargs) -> None:
        self.calls.append(("rectangle", args, kwargs))

    def create_oval(self, *args, **kwargs) -> None:
        self.calls.append(("oval", args, kwargs))

    def tag_lower(self, *args, **kwargs) -> None:
        self.calls.append(("tag_lower", args, kwargs))


class FakeScheduler:
    def __init__(self) -> None:
        self.jobs: dict[str, tuple[int, object]] = {}
        self.cancelled: list[str] = []
        self._next_id = 0

    def schedule(self, delay_ms: int, callback) -> str:
        self._next_id += 1
        job_id = f"job-{self._next_id}"
        self.jobs[job_id] = (delay_ms, callback)
        return job_id

    def cancel(self, job_id: str) -> None:
        self.cancelled.append(job_id)
        self.jobs.pop(job_id, None)

    def fire(self, job_id: str) -> None:
        _delay, callback = self.jobs.pop(job_id)
        callback()


def test_rgb_to_hex_formats_uppercase_hex() -> None:
    assert rgb_to_hex((0, 82, 184)) == "#0052B8"


@pytest.mark.parametrize("color", [(-1, 0, 0), (0, 256, 0), (0, 0, 1.5), (0, 0)])
def test_rgb_to_hex_rejects_invalid_rgb_values(color) -> None:
    with pytest.raises(ValueError):
        rgb_to_hex(color)


def test_surface_state_colors_accepts_partial_override() -> None:
    colors = SurfaceStateColors.from_mapping({"success": (1, 2, 3)})

    assert colors.hex("idle") == "#0052B8"
    assert colors.hex("success") == "#010203"


def test_flash_success_uses_one_second_then_resets_to_idle() -> None:
    applied: list[str] = []
    scheduler = FakeScheduler()
    controller = SurfaceFlashController(
        colors=SurfaceStateColors(),
        apply_color=applied.append,
        schedule=scheduler.schedule,
        cancel=scheduler.cancel,
    )

    controller.flash("success")

    assert controller.state == "success"
    assert applied == ["#00B04F"]
    job_id = next(iter(scheduler.jobs))
    assert scheduler.jobs[job_id][0] == 1000

    scheduler.fire(job_id)

    assert controller.state == "idle"
    assert applied[-1] == "#0052B8"


@pytest.mark.parametrize("state", ["error", "warning"])
def test_error_and_warning_flash_for_three_seconds(state) -> None:
    scheduler = FakeScheduler()
    controller = SurfaceFlashController(
        colors=SurfaceStateColors(),
        apply_color=lambda _color: None,
        schedule=scheduler.schedule,
        cancel=scheduler.cancel,
    )

    controller.flash(state)

    job_id = next(iter(scheduler.jobs))
    assert scheduler.jobs[job_id][0] == 3000


def test_new_flash_cancels_previous_pending_reset() -> None:
    applied: list[str] = []
    scheduler = FakeScheduler()
    controller = SurfaceFlashController(
        colors=SurfaceStateColors(),
        apply_color=applied.append,
        schedule=scheduler.schedule,
        cancel=scheduler.cancel,
    )

    controller.flash("warning")
    first_job = next(iter(scheduler.jobs))
    controller.flash("success")

    assert first_job in scheduler.cancelled
    assert first_job not in scheduler.jobs
    assert controller.state == "success"
    assert applied[-1] == "#00B04F"


def test_set_idle_cancels_pending_reset_without_scheduling_another() -> None:
    scheduler = FakeScheduler()
    controller = SurfaceFlashController(
        colors=SurfaceStateColors(),
        apply_color=lambda _color: None,
        schedule=scheduler.schedule,
        cancel=scheduler.cancel,
    )

    controller.flash("error")
    first_job = next(iter(scheduler.jobs))
    controller.set_state("idle")

    assert first_job in scheduler.cancelled
    assert scheduler.jobs == {}
    assert controller.state == "idle"


def test_rounded_surface_painter_redraws_tagged_surface_below_widgets() -> None:
    canvas = FakeCanvas()
    painter = RoundedSurfacePainter(
        canvas,
        width=100,
        height=60,
        background_color="#EEEEEE",
        surface_color="#FFFFFF",
        radius=10,
        inset=3,
    )

    painter.draw("#0052B8")

    assert canvas.calls[0] == ("delete", ("surface",), {})
    assert canvas.calls[-1] == ("tag_lower", ("surface",), {})
    shape_calls = [call for call in canvas.calls if call[0] in {"rectangle", "oval"}]
    assert len(shape_calls) == 13
    assert all(call[2]["tags"] == "surface" for call in shape_calls)


def test_drag_position_calculation_uses_recorded_offsets() -> None:
    class DialogLike:
        _drag_offset_x = 12
        _drag_offset_y = 5

    from ClipAI.ui.base_dialog import BaseDialog

    assert BaseDialog.calculate_drag_position(DialogLike(), 100, 80) == (88, 75)
