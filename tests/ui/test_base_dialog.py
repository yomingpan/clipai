from __future__ import annotations

from pathlib import Path
import inspect
import tkinter as tk

import customtkinter as ctk
import pytest
from customtkinter.windows.widgets.scaling.scaling_tracker import ScalingTracker

import ClipAI.ui.base_dialog as base_dialog_module

from ClipAI.core.models import PasteTarget
from ClipAI.ui.base_dialog import (
    ACTION_COLOR,
    ACTION_HOVER_COLOR,
    CONTENT_COLOR,
    CHECK_ICON,
    COPY_ICON,
    DISPLAY_BREAK_HINT,
    DISPLAY_BREAK_TAG,
    PASTE_ICON,
    POPUP_FONT_SIZES,
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
    TITLE_COLOR,
    StandardResultActions,
    SurfaceFlashController,
    SurfaceStateColors,
    BaseDialog,
    BaseResultSurface,
    _PresentationTextbox,
    apply_widget_font_scaling,
    rgb_to_hex,
    configure_presentation_typography,
    configure_display_break_typography,
    configure_hanging_indent,
    configure_tooltip_layer,
    insert_display_text,
    paste_target_display_text,
    _CanonicalSelectionSegment,
    _canonical_selection_text,
)
from ClipAI.ui.dialog_lifecycle import DialogLifecycle


def test_external_output_visibility_actions_are_mechanical() -> None:
    events = []

    class Window:
        def withdraw(self) -> None:
            events.append("withdraw")

        def deiconify(self) -> None:
            events.append("deiconify")

        def update_idletasks(self) -> None:
            pass

        def winfo_id(self) -> int:
            return 10

    class Lifecycle:
        def focus(self) -> bool:
            events.append("focus")
            return True

    dialog = BaseDialog.__new__(BaseDialog)
    dialog.root = Window()
    dialog.lifecycle = Lifecycle()
    class NativeWindowSurface:
        def show_without_activation(self, child_id: int) -> bool:
            events.append(("show_no_activate", child_id))
            return True

    dialog._native_window_surface = NativeWindowSurface()

    dialog.apply_external_output_visibility("hidden")
    dialog.apply_external_output_visibility("visible_activate")
    dialog.apply_external_output_visibility("visible_no_activate")

    assert events == [
        "withdraw",
        "deiconify",
        "focus",
        "deiconify",
        ("show_no_activate", 10),
    ]


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


def test_focus_idle_color_survives_transient_success_flash() -> None:
    applied: list[str] = []
    scheduler = FakeScheduler()
    controller = SurfaceFlashController(
        colors=SurfaceStateColors(),
        apply_color=applied.append,
        schedule=scheduler.schedule,
        cancel=scheduler.cancel,
    )

    controller.set_idle_color("#5F6B78")
    controller.flash("success")
    scheduler.fire(next(iter(scheduler.jobs)))

    assert applied[-1] == "#5F6B78"


def test_paste_target_display_uses_app_and_truncated_title() -> None:
    target = PasteTarget("hwnd:10", 42, "Notepad", "x" * 50, 1)

    assert paste_target_display_text(target) == f"Notepad — {'x' * 35}…"


def test_paste_focus_projection_explains_active_and_unfocused_ctrl_v() -> None:
    class Dialog:
        def __init__(self) -> None:
            self.focus_states = []

        def set_focus_active(self, active: bool) -> None:
            self.focus_states.append(active)

    class Label:
        def __init__(self) -> None:
            self.values = []

        def configure(self, **values) -> None:
            self.values.append(values)

    surface = BaseResultSurface.__new__(BaseResultSurface)
    surface.dialog = Dialog()
    surface.paste_target_label = Label()
    tooltips = []
    surface.set_action_tooltip = lambda slot, text: tooltips.append((slot, text))
    target = PasteTarget("hwnd:10", 42, "Notepad", "Untitled", 1)

    surface.set_paste_focus_state(True, target)
    surface.set_paste_focus_state(False, target)

    assert surface.dialog.focus_states == [True, False]
    assert surface.paste_target_label.values[0] == {"text": "貼到：Notepad — Untitled"}
    assert surface.paste_target_label.values[-1] == {"text": "未聚焦｜Ctrl+V 使用原剪貼簿"}
    assert tooltips[0] == ("paste", "貼上目前內容到 Notepad — Untitled")


def test_voice_draft_footer_explains_ctrl_v_for_editing_and_reading_modes() -> None:
    class Dialog:
        def set_focus_active(self, _active: bool) -> None:
            pass

    class Label:
        def __init__(self) -> None:
            self.values = []

        def configure(self, **values) -> None:
            self.values.append(values)

    surface = BaseResultSurface.__new__(BaseResultSurface)
    surface.dialog = Dialog()
    surface.paste_target_label = Label()
    tooltips = []
    surface.set_action_tooltip = lambda slot, text: tooltips.append((slot, text))
    target = PasteTarget("hwnd:10", 42, "Notepad", "Untitled", 1)

    surface.set_paste_focus_state(True, target, voice_draft_editing=True)
    surface.set_paste_focus_state(True, target, voice_draft_editing=False)

    assert surface.paste_target_label.values == [
        {"text": "編輯模式｜Ctrl+V 貼入｜Ctrl+Enter 閱讀"},
        {"text": "閱讀模式｜Ctrl+V → Notepad — Untitled｜Ctrl+Enter 編輯"},
    ]
    assert tooltips == [
        ("paste", "編輯模式：Ctrl+V 貼入草稿；Ctrl+Enter 切換閱讀模式"),
        ("paste", "閱讀模式：Ctrl+V 貼上目前內容到 Notepad — Untitled；Ctrl+Enter 切換編輯模式"),
    ]


def test_voice_draft_reading_mode_makes_content_read_only_until_reopened() -> None:
    class ContentText:
        def __init__(self) -> None:
            self.states = []
            self.bindings = {}

        def configure(self, **values) -> None:
            self.states.append(values["state"])

        def bind(self, sequence, callback) -> None:
            self.bindings[sequence] = callback

        def unbind(self, sequence) -> None:
            self.bindings.pop(sequence, None)

    surface = BaseResultSurface.__new__(BaseResultSurface)
    surface.content_text = ContentText()
    surface._editable_content_changed = lambda _text: None

    surface.set_voice_draft_editing(False)
    surface.set_voice_draft_editing(True)

    assert surface.content_text.states == ["disabled", "normal"]
    assert surface.content_text.bindings["<KeyRelease>"] == surface._notify_editable_content_changed


def test_voice_draft_content_refresh_preserves_the_current_caret() -> None:
    class ContentText:
        def __init__(self) -> None:
            self.text = "old draft"
            self.caret_updates = []

        def configure(self, **_values) -> None:
            pass

        def get(self, start, end) -> str:
            assert (start, end) == ("1.0", "end-1c")
            return self.text

        def index(self, mark) -> str:
            assert mark == "insert"
            return "1.4"

        def delete(self, _start, _end) -> None:
            self.text = ""

        def insert(self, _index, text, _tag) -> None:
            self.text = text

        def mark_set(self, mark, index) -> None:
            self.caret_updates.append((mark, index))

        def bind(self, _sequence, _callback) -> None:
            pass

    surface = BaseResultSurface.__new__(BaseResultSurface)
    surface.content_text = ContentText()
    surface._canonical_selection_segments = ()

    surface.set_editable_content("new authoritative draft", lambda _text: None)

    assert surface.content_text.caret_updates == [("insert", "1.4")]


def test_finalized_voice_insertion_moves_caret_to_inserted_text_end() -> None:
    class ContentText:
        def __init__(self) -> None:
            self.text = "first"
            self.caret_updates = []
            self.removed_tags = []

        def configure(self, **_values) -> None:
            pass

        def get(self, start, end) -> str:
            assert (start, end) == ("1.0", "end-1c")
            return self.text

        def index(self, mark) -> str:
            assert mark == "insert"
            return "1.0"

        def delete(self, _start, _end) -> None:
            self.text = ""

        def insert(self, _index, text, _tag) -> None:
            self.text = text

        def mark_set(self, mark, index) -> None:
            self.caret_updates.append((mark, index))

        def tag_remove(self, tag, start, end) -> None:
            self.removed_tags.append((tag, start, end))

        def bind(self, _sequence, _callback) -> None:
            pass

    surface = BaseResultSurface.__new__(BaseResultSurface)
    surface.content_text = ContentText()
    surface._canonical_selection_segments = ()

    surface.set_editable_content(
        "first second",
        lambda _text: None,
        caret_offset=len("first second"),
    )

    assert surface.content_text.caret_updates == [("insert", "1.0 + 12 chars")]
    assert surface.content_text.removed_tags == [("sel", "1.0", "end")]


def test_voice_draft_mode_shortcut_binds_directly_to_the_text_widget() -> None:
    class ContentText:
        def __init__(self) -> None:
            self.bindings = []

        def bind(self, sequence, callback, add=None) -> None:
            self.bindings.append((sequence, callback, add))

    callback = lambda _event: "break"
    surface = BaseResultSurface.__new__(BaseResultSurface)
    surface.content_text = ContentText()

    surface.bind_voice_draft_mode_toggle(callback)

    assert surface.content_text.bindings == [
        ("<Control-Return>", callback, "+"),
        ("<Control-KP_Enter>", callback, "+"),
    ]


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


def test_canvas_configure_drives_surface_from_observed_allocation() -> None:
    class Painter:
        def __init__(self) -> None:
            self.resize_call = None

        def resize(self, *args, **kwargs) -> None:
            self.resize_call = (args, kwargs)

    class Canvas:
        def __init__(self) -> None:
            self.coords_call = None
            self.itemconfigure_call = None

        def coords(self, *args) -> None:
            self.coords_call = args

        def itemconfigure(self, *args, **kwargs) -> None:
            self.itemconfigure_call = (args, kwargs)

    class Flash:
        def __init__(self) -> None:
            self.redraws = 0

        def redraw(self) -> None:
            self.redraws += 1

    dialog = BaseDialog.__new__(BaseDialog)
    dialog.width = 400
    dialog.height = 320
    dialog._surface_inset = 8
    dialog._corner_radius = 18
    dialog._border_inset = 2
    dialog._surface_window = "surface"
    dialog._painter = Painter()
    dialog.canvas = Canvas()
    dialog._flash_controller = Flash()

    dialog._on_canvas_configure(type("Event", (), {"width": 800, "height": 640})())

    assert dialog._painter.resize_call == ((800, 640), {"radius": 36, "inset": 4})
    assert dialog.canvas.coords_call == ("surface", 16, 16)
    assert dialog.canvas.itemconfigure_call == (("surface",), {"width": 768, "height": 608})
    assert dialog._flash_controller.redraws == 1


def test_dialog_never_precalculates_physical_widget_dimensions() -> None:
    source = inspect.getsource(BaseDialog)
    assert "_get_window_scaling" not in source
    assert 'bind("<Configure>", self._on_canvas_configure' in source


def test_dialog_initial_show_positions_and_resamples_while_withdrawn() -> None:
    source = inspect.getsource(BaseDialog.__init__)

    created = source.index("self.root =")
    withdrawn = source.index("self.root.withdraw()")
    positioned = source.index("self._position_window")
    laid_out = source.index("self.root.update_idletasks()")
    resampled = source.index("_resample_window_dpi_scaling(self.root)")
    shown = source.index("self.root.deiconify()")

    assert created < withdrawn < positioned < laid_out < resampled < shown
    assert "self.root.update()" not in source


def test_window_dpi_resample_updates_cache_before_widget_callbacks(monkeypatch) -> None:
    window = object()
    monkeypatch.setitem(ScalingTracker.window_dpi_scaling_dict, window, 1.5)
    observed_cache = []
    monkeypatch.setattr(
        ScalingTracker,
        "get_window_dpi_scaling",
        classmethod(lambda _cls, candidate: 1.0 if candidate is window else 1.5),
    )
    monkeypatch.setattr(
        ScalingTracker,
        "update_scaling_callbacks_for_window",
        classmethod(
            lambda cls, candidate: observed_cache.append(
                cls.window_dpi_scaling_dict[candidate]
            )
        ),
    )

    base_dialog_module._resample_window_dpi_scaling(window)

    assert ScalingTracker.window_dpi_scaling_dict[window] == 1.0
    assert observed_cache == [1.0]


def test_window_dpi_resample_rolls_back_cache_when_callback_fails(monkeypatch) -> None:
    window = object()
    monkeypatch.setitem(ScalingTracker.window_dpi_scaling_dict, window, 1.5)
    monkeypatch.setattr(
        ScalingTracker,
        "get_window_dpi_scaling",
        classmethod(lambda _cls, _window: 1.0),
    )

    def fail_callbacks(_cls, _window) -> None:
        raise RuntimeError("widget scaling failed")

    monkeypatch.setattr(
        ScalingTracker,
        "update_scaling_callbacks_for_window",
        classmethod(fail_callbacks),
    )

    with pytest.raises(RuntimeError, match="widget scaling failed"):
        base_dialog_module._resample_window_dpi_scaling(window)

    assert ScalingTracker.window_dpi_scaling_dict[window] == 1.5


def test_dialog_resize_only_requests_logical_window_geometry() -> None:
    class Root:
        geometry_call = None

        def winfo_x(self):
            return 10

        def winfo_y(self):
            return 20

        def geometry(self, value):
            self.geometry_call = value

    dialog = BaseDialog.__new__(BaseDialog)
    dialog.width = 400
    dialog.height = 320
    dialog.root = Root()

    dialog.resize(500, 400)

    assert dialog.root.geometry_call == "500x400+10+20"
    assert (dialog.width, dialog.height) == (500, 400)


def test_dialog_is_alive_requires_valid_open_existing_root() -> None:
    class Lifecycle:
        is_closed = False

    class Root:
        def __init__(self, result=True, error=False) -> None:
            self.result = result
            self.error = error

        def winfo_exists(self):
            if self.error:
                raise tk.TclError("destroyed")
            return self.result

    dialog = BaseDialog.__new__(BaseDialog)
    dialog._valid = True
    dialog.lifecycle = Lifecycle()
    dialog.root = Root()
    assert dialog.is_alive() is True

    dialog.lifecycle.is_closed = True
    assert dialog.is_alive() is False
    dialog.lifecycle.is_closed = False
    dialog.root = Root(False)
    assert dialog.is_alive() is False
    dialog.root = Root(error=True)
    assert dialog.is_alive() is False
    dialog._valid = False
    dialog.root = Root()
    assert dialog.is_alive() is False


def test_dialog_screen_bounds_include_only_points_inside_popup() -> None:
    class Root:
        def update_idletasks(self):
            pass

        def winfo_rootx(self):
            return 100

        def winfo_rooty(self):
            return 200

        def winfo_width(self):
            return 300

        def winfo_height(self):
            return 150

    dialog = BaseDialog.__new__(BaseDialog)
    dialog.root = Root()

    assert dialog.contains_screen_point(100, 200) is True
    assert dialog.contains_screen_point(399, 349) is True
    assert dialog.contains_screen_point(400, 350) is False


def test_dialog_visibility_uses_toolkit_viewable_truth() -> None:
    dialog = BaseDialog.__new__(BaseDialog)
    dialog.root = type("Root", (), {"winfo_viewable": lambda _self: 1})()
    assert dialog.is_visible() is True


def test_dialog_lifecycle_exposes_closed_state() -> None:
    class Root:
        def destroy(self):
            pass

        def quit(self):
            pass

    lifecycle = DialogLifecycle(Root())
    assert lifecycle.is_closed is False
    lifecycle.close()
    assert lifecycle.is_closed is True


def test_dialog_lifecycle_focus_reports_verified_toolkit_focus() -> None:
    class Root:
        def __init__(self) -> None:
            self.focused = None
            self.events = []

        def update_idletasks(self) -> None:
            self.events.append("layout")

        def lift(self) -> None:
            self.events.append("lift")

        def focus_get(self):
            return self.focused

    class Widget:
        def __init__(self, root) -> None:
            self.root = root

        def focus_force(self) -> None:
            self.root.focused = self

        def winfo_toplevel(self):
            return self.root

    root = Root()
    widget = Widget(root)
    lifecycle = DialogLifecycle(root)

    assert lifecycle.focus(widget) is True
    assert root.events == ["layout", "lift"]


def test_dialog_lifecycle_requires_native_window_activation_when_configured() -> None:
    class Root:
        def __init__(self) -> None:
            self.focused = None

        def update_idletasks(self) -> None:
            pass

        def lift(self) -> None:
            pass

        def focus_get(self):
            return self.focused

    class Widget:
        def __init__(self, root) -> None:
            self.root = root

        def focus_force(self) -> None:
            self.root.focused = self

        def winfo_toplevel(self):
            return self.root

    root = Root()
    widget = Widget(root)
    native_activations = []
    lifecycle = DialogLifecycle(
        root,
        window_activator=lambda window: native_activations.append(window) or False,
    )

    assert lifecycle.focus(widget) is False
    assert native_activations == [root]


def test_native_close_request_uses_callback_instead_of_destroying_the_dialog() -> None:
    events: list[str] = []
    dialog = BaseDialog.__new__(BaseDialog)
    dialog._on_close_request = lambda: events.append("close-requested")
    dialog.close = lambda: events.append("destroyed")

    assert dialog.request_close() == "break"
    assert events == ["close-requested"]


def test_result_surface_escape_defers_to_the_global_gesture_owner() -> None:
    events: list[str] = []
    surface = BaseResultSurface.__new__(BaseResultSurface)
    surface._feedback_overlay_open = False
    surface.dialog = type("Dialog", (), {"request_close": lambda _self: events.append("close")})()

    assert surface._handle_escape() == "break"
    assert events == []


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
        "Speak result (Ctrl+Q)",
        "Copy result (Ctrl+C)",
        "Paste result to target",
        "Archive result (Ctrl+S)",
        "Ask follow-up (Ctrl+/)",
    ]
    assert [spec.active_tooltip for spec in STANDARD_RESULT_ACTIONS] == [
        "Stop speaking (Ctrl+Q)",
        "Copy accepted (Ctrl+C)",
        None,
        "Archive accepted (Ctrl+S)",
        "Close follow-up (Ctrl+/)",
    ]


def test_primary_and_overflow_action_placement_is_stable() -> None:
    primary = [spec.slot_id for spec in STANDARD_RESULT_ACTIONS if spec.slot_id not in {"paste", "archive"}]
    overflow = [spec.slot_id for spec in STANDARD_RESULT_ACTIONS if spec.slot_id in {"paste", "archive"}]
    assert primary == ["speaker", "copy", "follow_up"]
    assert overflow == ["paste", "archive"]


def test_presentation_tags_avoid_customtkinter_forbidden_font_option() -> None:
    assert all("font" not in style for style in PRESENTATION_TAG_STYLES.values())


def test_presentation_typography_creates_clear_heading_and_inline_hierarchy() -> None:
    assert POPUP_FONT_SIZES == {
        "auxiliary": 11,
        "model": 9,
        "interface": 12,
        "content": 14,
        "heading_3": 15,
        "heading_2": 16,
        "heading_1": 18,
        "tooltip": 12,
    }
    assert PRESENTATION_TAG_FONTS["bold"][1] == POPUP_FONT_SIZES["content"]
    assert PRESENTATION_TAG_FONTS["italic"][1] == POPUP_FONT_SIZES["content"]
    assert PRESENTATION_TAG_FONTS["heading_1"][1] > PRESENTATION_TAG_FONTS["heading_2"][1]
    assert PRESENTATION_TAG_FONTS["heading_2"][1] > PRESENTATION_TAG_FONTS["heading_3"][1]
    assert PRESENTATION_TAG_FONTS["heading_1"][2] == "bold"
    assert PRESENTATION_TAG_FONTS["bold"][2] == "bold"
    assert PRESENTATION_TAG_FONTS["italic"][2] == "italic"
    assert PRESENTATION_TAG_STYLES["heading_1"]["foreground"] != PRESENTATION_TAG_STYLES["italic"]["foreground"]


def test_popup_title_uses_the_primary_content_heading_color() -> None:
    assert TITLE_COLOR == PRESENTATION_TAG_STYLES["heading_1"]["foreground"]


def test_presentation_typography_is_applied_at_tk_adapter_seam() -> None:
    class TkText:
        def __init__(self) -> None:
            self.configured = {}

        def tag_configure(self, tag, **options):
            self.configured[tag] = options

    tk_text = TkText()
    class Textbox:
        _textbox = tk_text

        def _apply_font_scaling(self, font):
            return (font[0], -font[1] * 2, font[2:])

    textbox = Textbox()

    assert configure_presentation_typography(textbox) is True
    assert tk_text.configured["heading_1"]["font"] == (TC_FONT_FAMILY, -36, "bold")
    assert tk_text.configured["bold"]["font"][-1] == "bold"
    assert tk_text.configured["italic"]["font"][-1] == "italic"


def test_widget_font_scaling_requires_owning_ctk_widget() -> None:
    class Widget:
        def _apply_font_scaling(self, font):
            return (font[0], -18)

    assert apply_widget_font_scaling(Widget(), (TC_FONT_FAMILY, 9)) == (TC_FONT_FAMILY, -18)

    class StyledWidget:
        def _apply_font_scaling(self, font):
            return (font[0], -30, ("bold",))

    assert apply_widget_font_scaling(StyledWidget(), (TC_FONT_FAMILY, 15, "bold")) == (
        TC_FONT_FAMILY,
        -30,
        "bold",
    )
    with pytest.raises(AttributeError):
        apply_widget_font_scaling(object(), (TC_FONT_FAMILY, 9))


def test_presentation_textbox_reapplies_tags_after_scaling(monkeypatch) -> None:
    calls: list[tuple] = []
    monkeypatch.setattr(ctk.CTkTextbox, "_set_scaling", lambda self, *args, **kwargs: calls.append((args, kwargs)))
    monkeypatch.setattr(
        "ClipAI.ui.base_dialog.configure_presentation_typography",
        lambda textbox: calls.append(("typography", textbox)) or True,
    )
    textbox = _PresentationTextbox.__new__(_PresentationTextbox)
    textbox._textbox = object()

    textbox._set_scaling(1.5, 1.5)

    assert calls[0] == ((1.5, 1.5), {})
    assert calls[1] == ("typography", textbox)


def test_presentation_typography_safely_degrades_without_tk_text_widget() -> None:
    assert configure_presentation_typography(object()) is False


def test_display_break_spaces_are_inserted_with_a_one_pixel_adapter_tag() -> None:
    class TkText:
        def __init__(self) -> None:
            self.configured = {}

        def tag_configure(self, tag, **options) -> None:
            self.configured[tag] = options

    class Textbox:
        _textbox = TkText()

        def __init__(self) -> None:
            self.insertions = []

        def insert(self, index, text, tags) -> None:
            self.insertions.append((index, text, tags))

    textbox = Textbox()
    assert configure_display_break_typography(textbox) is True
    insert_display_text(textbox, "end", "中文", "body")

    assert textbox._textbox.configured[DISPLAY_BREAK_TAG]["font"] == (TC_FONT_FAMILY, -1)
    assert textbox.insertions[1][2] == ("body", DISPLAY_BREAK_TAG)
    assert " " in textbox.insertions[1][1]


def test_long_cjk_text_is_batched_into_one_native_tk_insert_call() -> None:
    class NativeText:
        def __init__(self) -> None:
            self.calls = []

        def insert(self, *args) -> None:
            self.calls.append(args)

    class Textbox:
        def __init__(self) -> None:
            self._textbox = NativeText()

        def insert(self, *args) -> None:
            raise AssertionError("native batched insert should be used")

    textbox = Textbox()
    insert_display_text(textbox, "end", "漢字" * 5000, "body")
    assert len(textbox._textbox.calls) == 1


def test_stream_append_preserves_scroll_and_does_not_replace_existing_text() -> None:
    class Textbox:
        def __init__(self) -> None:
            self.calls = []

        def yview(self):
            return (0.1, 0.5)

        def configure(self, **kwargs):
            self.calls.append(("configure", kwargs))

        def insert(self, *args):
            self.calls.append(("insert", args))

        def delete(self, *args):
            self.calls.append(("delete", args))

        def see(self, *args):
            self.calls.append(("see", args))

    surface = BaseResultSurface.__new__(BaseResultSurface)
    surface.content_text = Textbox()
    surface.append_content_text("next", "body")

    assert not any(call[0] == "delete" for call in surface.content_text.calls)
    assert not any(call[0] == "see" for call in surface.content_text.calls)
    assert any(call[0] == "insert" for call in surface.content_text.calls)


def test_canonical_selection_restores_markdown_bullets_and_inline_styles() -> None:
    segments = (
        _CanonicalSelectionSegment(0, "• ", "- "),
        _CanonicalSelectionSegment(2, "First", "**First**"),
        _CanonicalSelectionSegment(7, " item", " item"),
        _CanonicalSelectionSegment(12, "\n", "\n"),
        _CanonicalSelectionSegment(13, "• ", "- "),
        _CanonicalSelectionSegment(15, "Second", "*Second*"),
    )

    assert _canonical_selection_text(segments, 0, 21) == "- **First** item\n- *Second*"


def test_presentation_surface_returns_canonical_markdown_for_rendered_selection() -> None:
    from ClipAI.services.presentation import MarkdownPresentationParser

    class Textbox:
        def __init__(self) -> None:
            self.text = ""
            self.selection = (0, 0)

        def configure(self, **_kwargs) -> None:
            pass

        def delete(self, *_args) -> None:
            self.text = ""

        def insert(self, _index, text, _tags) -> None:
            self.text += text

        def get(self, start, end) -> str:
            first, last = self.selection
            if (start, end) == ("sel.first", "sel.last"):
                return self.text[first:last]
            if (start, end) == ("1.0", "sel.first"):
                return self.text[:first]
            raise AssertionError((start, end))

    surface = BaseResultSurface.__new__(BaseResultSurface)
    surface.content_text = Textbox()
    surface._list_indent_prefixes = {}
    surface.set_presentation_document(
        MarkdownPresentationParser().parse("- **First** item\n- *Second*")
    )
    surface.content_text.selection = (0, len(surface.content_text.text.rstrip("\n")))

    assert surface.selected_text() == "- **First** item\n- *Second*"


def test_presentation_surface_projects_double_clicked_word_without_partial_break_hints() -> None:
    class Textbox:
        def get(self, start, end) -> str:
            if (start, end) == ("sel.first", "sel.last"):
                # Tk's word selection starts and ends inside the adjacent
                # U+2063 SPACE U+2063 display-only break hints.
                return "\u2063appetizer\u2063"
            if (start, end) == ("1.0", "sel.first"):
                return f"prefix{DISPLAY_BREAK_HINT} {DISPLAY_BREAK_HINT[:2]}"
            raise AssertionError((start, end))

    surface = BaseResultSurface.__new__(BaseResultSurface)
    surface.content_text = Textbox()
    surface._canonical_selection_segments = (
        _CanonicalSelectionSegment(0, "prefix appetizer pronunciation", "prefix appetizer pronunciation"),
    )

    assert surface.selected_text() == "appetizer"


@pytest.mark.parametrize(
    ("source", "expected"),
    (
        ("A I", "I"),
        (
            "- I went from [not doing X] to [basically doing Y].",
            "I went from [not doing X] to [basically doing Y].",
        ),
    ),
)
def test_presentation_surface_preserves_selection_after_a_semantic_space(
    source: str,
    expected: str,
) -> None:
    from ClipAI.services.presentation import MarkdownPresentationParser

    class Textbox:
        def __init__(self) -> None:
            self.text = ""
            self.selection = (0, 0)

        def configure(self, **_kwargs) -> None:
            pass

        def delete(self, *_args) -> None:
            self.text = ""

        def insert(self, _index, text, _tags) -> None:
            self.text += text

        def get(self, start, end) -> str:
            first, last = self.selection
            if (start, end) == ("sel.first", "sel.last"):
                return self.text[first:last]
            if (start, end) == ("1.0", "sel.first"):
                return self.text[:first]
            raise AssertionError((start, end))

    surface = BaseResultSurface.__new__(BaseResultSurface)
    surface.content_text = Textbox()
    surface._list_indent_prefixes = {}
    surface.set_presentation_document(MarkdownPresentationParser().parse(source))
    selected_character = surface.content_text.text.index("I")
    boundary_hint = surface.content_text.text.rfind(
        DISPLAY_BREAK_HINT,
        0,
        selected_character,
    )
    surface.content_text.selection = (
        boundary_hint,
        surface.content_text.text.index("\n", selected_character),
    )

    assert surface.selected_text() == expected


def test_presentation_surface_renders_retrieval_spacer_without_showing_marker() -> None:
    from ClipAI.services.presentation import MarkdownPresentationParser

    class Textbox:
        def __init__(self) -> None:
            self.text = ""
            self.insertions = []

        def configure(self, **_kwargs) -> None:
            pass

        def delete(self, *_args) -> None:
            self.text = ""
            self.insertions.clear()

        def insert(self, _index, text, tags) -> None:
            self.text += text
            self.insertions.append((text, tags))

    surface = BaseResultSurface.__new__(BaseResultSurface)
    surface.content_text = Textbox()
    surface._list_indent_prefixes = {}
    surface.set_presentation_document(
        MarkdownPresentationParser().parse(
            "## Retrieve\n\nTry first.\n\n[[SCROLL_FOR_ANSWER]]\n\nAnswer: Use it."
        )
    )

    assert "[[SCROLL_FOR_ANSWER]]" not in surface.content_text.text
    assert any(text == "\n" * 8 and "retrieval_spacer" in tags for text, tags in surface.content_text.insertions)


@pytest.mark.parametrize("scale", [1.0, 1.33, 2.0])
def test_hanging_indent_tracks_measured_prefix_width_at_each_dpi_scale(monkeypatch, scale) -> None:
    class TkText:
        def __init__(self) -> None:
            self.configured = {}

        def tag_configure(self, tag, **options) -> None:
            self.configured[tag] = options

    class Textbox:
        _textbox = TkText()

        def _apply_font_scaling(self, font):
            return (font[0], -round(font[1] * scale))

    class Font:
        def __init__(self, *, root, font) -> None:
            self.font = font

        def measure(self, prefix: str) -> int:
            return len(prefix) * abs(self.font[1])

    monkeypatch.setattr("ClipAI.ui.base_dialog.tkfont.Font", Font)
    textbox = Textbox()
    assert configure_hanging_indent(textbox, "item", "12. ") is True
    assert textbox._textbox.configured["item"] == {
        "lmargin1": 0,
        "lmargin2": len("12. ") * round(POPUP_FONT_SIZES["content"] * scale),
    }


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


def test_pin_state_updates_icon_and_shortcut_tooltip() -> None:
    class Dialog:
        def __init__(self) -> None:
            self.pinned = None

        def set_pinned(self, pinned: bool) -> None:
            self.pinned = pinned

    class Button:
        def __init__(self) -> None:
            self.configuration = {}

        def configure(self, **configuration) -> None:
            self.configuration = configuration

    class Tooltip:
        def __init__(self) -> None:
            self.text = ""

        def set_text(self, text: str) -> None:
            self.text = text

    surface = BaseResultSurface.__new__(BaseResultSurface)
    surface.dialog = Dialog()
    surface.pin_button = Button()
    surface._pin_tooltip = Tooltip()

    surface.set_pinned_state(True)
    assert surface.dialog.pinned is True
    assert surface.pin_button.configuration["text"] == UNPIN_ICON
    assert surface._pin_tooltip.text == "Unpin (Ctrl+E or double-click header)"

    surface.set_pinned_state(False)
    assert surface.dialog.pinned is False
    assert surface.pin_button.configuration["text"] == PIN_ICON
    assert surface._pin_tooltip.text == "Keep open (Ctrl+E or double-click header)"


def test_repeated_pin_projection_does_not_redraw_button() -> None:
    class Dialog:
        def __init__(self) -> None:
            self.pinned = False

        def set_pinned(self, pinned: bool) -> None:
            self.pinned = pinned

    class Button:
        def __init__(self) -> None:
            self.configurations = []

        def configure(self, **configuration) -> None:
            self.configurations.append(configuration)

    class Tooltip:
        def __init__(self) -> None:
            self.texts = []

        def set_text(self, text: str) -> None:
            self.texts.append(text)

    surface = BaseResultSurface.__new__(BaseResultSurface)
    surface.dialog = Dialog()
    surface.pin_button = Button()
    surface._pin_tooltip = Tooltip()

    surface.set_pinned_state(True)
    surface.set_pinned_state(True)

    assert len(surface.pin_button.configurations) == 1
    assert surface._pin_tooltip.texts == ["Unpin (Ctrl+E or double-click header)"]


def test_header_double_click_binding_excludes_action_buttons() -> None:
    class Widget:
        def __init__(self) -> None:
            self.bindings = []

        def bind(self, sequence, callback, add=None) -> None:
            self.bindings.append((sequence, callback, add))

    callback = lambda _event: None
    surface = BaseResultSurface.__new__(BaseResultSurface)
    surface.header = Widget()
    surface.title_area = Widget()
    surface.title_label = Widget()
    surface.pin_button = Widget()
    surface.close_button = Widget()

    surface.bind_header_double_click(callback)

    for widget in (surface.header, surface.title_area, surface.title_label):
        assert widget.bindings == [("<Double-Button-1>", callback, "+")]
    assert surface.pin_button.bindings == []
    assert surface.close_button.bindings == []


def test_source_preview_stays_on_one_line_and_ellipsizes_over_limit() -> None:
    from ClipAI.ui.base_dialog import SOURCE_PREVIEW_MAX_CHARS, BaseResultSurface, ellipsize_source_preview

    assert SOURCE_PREVIEW_MAX_CHARS == 36
    text = "Clipboard: " + "a" * SOURCE_PREVIEW_MAX_CHARS
    preview = ellipsize_source_preview(text)
    assert len(preview) == SOURCE_PREVIEW_MAX_CHARS
    assert preview.endswith("...")
    source = inspect.getsource(BaseResultSurface._build)
    assert "wraplength=0" in source
    assert 'self.footer.grid(row=5, column=0, sticky="ew"' in source
    assert 'self.paste_target_label.grid(row=0, column=0, sticky="w")' in source
    assert 'self.model_label.grid(row=0, column=1, sticky="e"' in source
    assert 'height=11' in source
    assert source.count('size=POPUP_FONT_SIZES["model"]') == 2
    assert source.count("text_color=MODEL_COLOR") == 2
    assert "\n" not in preview


def test_source_preview_at_limit_is_not_ellipsized() -> None:
    from ClipAI.ui.base_dialog import SOURCE_PREVIEW_MAX_CHARS, ellipsize_source_preview

    text = "a" * SOURCE_PREVIEW_MAX_CHARS
    assert ellipsize_source_preview(text) == text


def test_action_contract_tooltip_explains_ai_scope_and_feedback_entry_points() -> None:
    from ClipAI.core.models import ActionFeedbackContract, FeedbackReason
    from ClipAI.ui.base_dialog import action_contract_tooltip_text

    text = action_contract_tooltip_text(ActionFeedbackContract(
        "縮短內容",
        "不替你改變原本的立場與語氣",
        (FeedbackReason("other", "其他"),),
    ))

    assert text == (
        "AI 幫你\n縮短內容\n\n"
        "AI 不做什麼\n不替你改變原本的立場與語氣\n\n"
        "若結果不符合預期，可按右上角 ⓘ 或 Ctrl + R 回饋。"
    )


def test_edge_tts_dependency_has_known_working_lower_bound() -> None:
    pyproject = Path(__file__).parents[2] / "pyproject.toml"
    assert '"edge-tts>=7.2.8"' in pyproject.read_text(encoding="utf-8")
