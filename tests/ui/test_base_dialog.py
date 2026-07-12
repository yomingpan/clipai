from __future__ import annotations

import pytest

from ClipAI.ui.base_dialog import (
    ACTION_COLOR,
    ACTION_HOVER_COLOR,
    CONTENT_COLOR,
    CHECK_ICON,
    COPY_ICON,
    PASTE_ICON,
    PRESENTATION_TAG_FONTS,
    PRESENTATION_TAG_STYLES,
    PIN_ICON,
    UNPIN_ICON,
    ARCHIVE_ICON,
    FOLLOW_ACTIVE_COLOR,
    FOLLOW_UP_ICON,
    RoundedSurfacePainter,
    SPEAKER_ICON,
    SPEAKER_ACTIVE_COLOR,
    SPEAKER_ACTIVE_HOVER_COLOR,
    STANDARD_RESULT_ACTIONS,
    STOP_ICON,
    TC_FONT_FAMILY,
    StandardResultActions,
    SurfaceFlashController,
    SurfaceStateColors,
    hide_window_from_task_switcher,
    rgb_to_hex,
    configure_presentation_typography,
    configure_tooltip_layer,
)


def test_windows_tool_window_style_hides_taskbar_and_alt_tab() -> None:
    class Window:
        def update_idletasks(self):
            pass

        def winfo_id(self):
            return 10

    class User32:
        def __init__(self):
            self.style = 0x00040000
            self.updated = None
            self.positioned = None

        def GetParent(self, hwnd):
            return 20

        def GetWindowLongW(self, hwnd, index):
            assert (hwnd, index) == (20, -20)
            return self.style

        def SetWindowLongW(self, hwnd, index, style):
            self.updated = (hwnd, index, style)

        def SetWindowPos(self, *args):
            self.positioned = args

    user32 = User32()
    assert hide_window_from_task_switcher(Window(), user32) is True
    assert user32.updated == (20, -20, 0x00000080)
    assert user32.positioned[-1] == 0x0027


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
    assert rgb_to_hex((0, 119, 200)) == "#0077C8"


@pytest.mark.parametrize("color", [(-1, 0, 0), (0, 256, 0), (0, 0, 1.5), (0, 0)])
def test_rgb_to_hex_rejects_invalid_rgb_values(color) -> None:
    with pytest.raises(ValueError):
        rgb_to_hex(color)


def test_surface_state_colors_accepts_partial_override() -> None:
    colors = SurfaceStateColors.from_mapping({"success": (1, 2, 3)})

    assert colors.hex("idle") == "#0077C8"
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
    assert applied[-1] == "#0077C8"


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


def test_redraw_preserves_pending_success_reset() -> None:
    applied: list[str] = []
    scheduler = FakeScheduler()
    controller = SurfaceFlashController(
        colors=SurfaceStateColors(),
        apply_color=applied.append,
        schedule=scheduler.schedule,
        cancel=scheduler.cancel,
    )
    controller.flash("success")
    job_id = next(iter(scheduler.jobs))
    controller.redraw()
    assert job_id in scheduler.jobs
    assert scheduler.cancelled == []
    scheduler.fire(job_id)
    assert controller.state == "idle"


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

    painter.draw("#0077C8")

    assert canvas.calls[0] == ("delete", ("surface",), {})
    assert canvas.calls[-1] == ("tag_lower", ("surface",), {})
    shape_calls = [call for call in canvas.calls if call[0] in {"rectangle", "oval"}]
    assert len(shape_calls) == 13
    assert all(call[2]["tags"] == "surface" for call in shape_calls)


def test_rounded_surface_painter_resize_updates_future_draw_bounds() -> None:
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
    painter.resize(200, 120)
    painter.draw("#0077C8")
    coordinates = [call[1] for call in canvas.calls if call[0] in {"rectangle", "oval"}]
    assert any(200 in values or 197 in values for values in coordinates)


def test_drag_position_calculation_uses_recorded_offsets() -> None:
    class DialogLike:
        _drag_offset_x = 12
        _drag_offset_y = 5

    from ClipAI.ui.base_dialog import BaseDialog

    assert BaseDialog.calculate_drag_position(DialogLike(), 100, 80) == (88, 75)


def test_standard_result_actions_expose_trusted_slots_in_order() -> None:
    assert [spec.slot_id for spec in STANDARD_RESULT_ACTIONS] == ["speaker", "copy", "paste", "archive", "follow_up"]
    assert [spec.icon for spec in STANDARD_RESULT_ACTIONS] == [
        SPEAKER_ICON,
        COPY_ICON,
        PASTE_ICON,
        ARCHIVE_ICON,
        FOLLOW_UP_ICON,
    ]
    assert [spec.tooltip for spec in STANDARD_RESULT_ACTIONS] == [
        "Speak result",
        "Copy result",
        "Paste result",
        "Archive result",
        "Ask follow-up",
    ]


def test_primary_and_overflow_action_placement_is_stable() -> None:
    primary = [spec.slot_id for spec in STANDARD_RESULT_ACTIONS if spec.slot_id not in {"paste", "archive"}]
    overflow = [spec.slot_id for spec in STANDARD_RESULT_ACTIONS if spec.slot_id in {"paste", "archive"}]
    assert primary == ["speaker", "copy", "follow_up"]
    assert overflow == ["paste", "archive"]


def test_presentation_tags_avoid_customtkinter_forbidden_font_option() -> None:
    assert all("font" not in style for style in PRESENTATION_TAG_STYLES.values())


def test_presentation_typography_creates_clear_heading_and_inline_hierarchy() -> None:
    assert PRESENTATION_TAG_FONTS["heading_1"][1] > PRESENTATION_TAG_FONTS["heading_2"][1]
    assert PRESENTATION_TAG_FONTS["heading_2"][1] > PRESENTATION_TAG_FONTS["heading_3"][1]
    assert PRESENTATION_TAG_FONTS["heading_1"][2] == "bold"
    assert PRESENTATION_TAG_FONTS["bold"][2] == "bold"
    assert PRESENTATION_TAG_FONTS["italic"][2] == "italic"
    assert PRESENTATION_TAG_STYLES["heading_1"]["foreground"] != PRESENTATION_TAG_STYLES["italic"]["foreground"]


def test_presentation_typography_is_applied_at_tk_adapter_seam() -> None:
    class TkText:
        def __init__(self) -> None:
            self.configured = {}

        def tag_configure(self, tag, **options):
            self.configured[tag] = options

    tk_text = TkText()
    textbox = type("Textbox", (), {"_textbox": tk_text})()

    assert configure_presentation_typography(textbox) is True
    assert tk_text.configured["heading_1"]["font"] == (TC_FONT_FAMILY, 15, "bold")
    assert tk_text.configured["bold"]["font"][-1] == "bold"
    assert tk_text.configured["italic"]["font"][-1] == "italic"


def test_presentation_typography_safely_degrades_without_tk_text_widget() -> None:
    assert configure_presentation_typography(object()) is False


def test_tooltip_layer_is_transient_and_above_popup() -> None:
    calls: list[tuple] = []

    class Window:
        def wm_transient(self, owner):
            calls.append(("transient", owner))

        def attributes(self, *args):
            calls.append(("attributes", *args))

        def lift(self, owner):
            calls.append(("lift", owner))

    owner = object()
    configure_tooltip_layer(Window(), owner)
    assert calls == [
        ("transient", owner),
        ("attributes", "-topmost", True),
        ("lift", owner),
    ]


def test_standard_result_action_idle_style_is_uniform() -> None:
    spec = STANDARD_RESULT_ACTIONS[0]

    assert StandardResultActions.style_for(spec, False) == {
        "text": SPEAKER_ICON,
        "fg_color": ACTION_COLOR,
        "hover_color": ACTION_HOVER_COLOR,
        "text_color": CONTENT_COLOR,
    }


def test_standard_result_action_active_styles_are_semantic() -> None:
    speaker = STANDARD_RESULT_ACTIONS[0]
    follow_up = STANDARD_RESULT_ACTIONS[-1]

    assert StandardResultActions.style_for(speaker, True) == {
        "text": STOP_ICON,
        "fg_color": SPEAKER_ACTIVE_COLOR,
        "hover_color": SPEAKER_ACTIVE_HOVER_COLOR,
        "text_color": CONTENT_COLOR,
    }
    assert StandardResultActions.style_for(follow_up, True) == {
        "text": FOLLOW_UP_ICON,
        "fg_color": FOLLOW_ACTIVE_COLOR,
        "hover_color": ACTION_HOVER_COLOR,
        "text_color": CONTENT_COLOR,
    }


def test_repeated_action_pulse_restarts_feedback_timer() -> None:
    class Lifecycle:
        def __init__(self) -> None:
            self.scheduled: list[tuple[int, object]] = []
            self.cancelled: list[str] = []

        def schedule(self, delay_ms, callback):
            job = f"job-{len(self.scheduled) + 1}"
            self.scheduled.append((delay_ms, callback))
            return job

        def cancel(self, job):
            self.cancelled.append(job)

    class Button:
        def configure(self, **kwargs):
            pass

    class Surface:
        def __init__(self) -> None:
            self.dialog = type("Dialog", (), {"lifecycle": Lifecycle()})()

        def add_action_slot(self, *args, **kwargs):
            return Button()

        def set_action_tooltip(self, slot_id, text):
            pass

    surface = Surface()
    actions = StandardResultActions(surface)
    actions.pulse("copy")
    actions.pulse("copy")

    assert surface.dialog.lifecycle.cancelled == ["job-1"]
    assert [delay for delay, _callback in surface.dialog.lifecycle.scheduled] == [1000, 1000]


def test_copy_and_archive_feedback_use_green_check_icon() -> None:
    copy = STANDARD_RESULT_ACTIONS[1]
    archive = STANDARD_RESULT_ACTIONS[3]

    for spec in (copy, archive):
        style = StandardResultActions.style_for(spec, True)
        assert style["text"] == CHECK_ICON
        assert style["fg_color"] == "#00B04F"


def test_pin_icons_use_stable_icon_font_glyphs() -> None:
    assert PIN_ICON == "\uE718"
    assert UNPIN_ICON == "\uE77A"
