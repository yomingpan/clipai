from dataclasses import replace
import tkinter as tk

import pytest

from ClipAI.core.models import DisplayMetrics
from ClipAI.core.voice import InlineDictationView
from ClipAI.ui.inline_pill import InlinePill, resolve_pill_layout


@pytest.mark.parametrize("scale", [1, 1.25, 1.5, 2])
@pytest.mark.parametrize("pointer", [(0, 0), (1279, 719), (600, 300)])
def test_pill_and_future_panel_fit_work_area_with_scaled_margin(scale, pointer):
    metrics = DisplayMetrics(scale, 0, 0, 1280, 720, *pointer)
    layout = resolve_pill_layout(metrics, "cursor")
    assert layout.x >= round(8*scale)
    assert layout.y >= round(8*scale)
    assert layout.x + layout.width <= 1280-round(8*scale)
    assert layout.y + layout.height <= 720-round(8*scale)
    assert layout.scale == scale


@pytest.mark.parametrize("scale", [1, 1.25, 1.5, 1.75, 2])
def test_scaled_regions_fit_without_independent_rounding_clipping(scale):
    from ClipAI.ui import voice_visuals as visuals
    metrics = DisplayMetrics(scale, 0, 0, 1600, 1000, 0, 0)
    layout = resolve_pill_layout(metrics, "bottom_center")
    assert layout.pill_y+round(visuals.BASE_HEIGHT*scale) == layout.height
    assert layout.pill_y-round(visuals.STRIP_HEIGHT*scale) == round(visuals.PANEL_HEIGHT*scale)


def test_bottom_center_placement_does_not_follow_pointer():
    metrics = DisplayMetrics(1, 100, 50, 1000, 700, 130, 70)
    assert resolve_pill_layout(metrics, "bottom_center") == resolve_pill_layout(replace(metrics, cursor_x=1000, cursor_y=700), "bottom_center")


@pytest.mark.parametrize("scale", [1, 1.5, 2])
def test_button_targets_follow_spaced_geometry_and_leave_shell_and_gap_inactive(scale):
    pill = object.__new__(InlinePill)
    pill._layout = layout = resolve_pill_layout(DisplayMetrics(scale, 0, 0, 1600, 1000, 0, 0), "bottom_center")
    def hit(x, y):
        return pill._hit(layout.pill_x+x*scale, layout.pill_y+y*scale)
    assert hit(18, 18) == "cancel"
    assert hit(110, 18) == "refine"
    assert hit(142, 18) == "raw"
    assert hit(126, 18) == ""
    assert hit(110, 0) == hit(110, 36) == ""
    assert hit(0, 18) == hit(160, 18) == ""


@pytest.fixture(scope="module")
def root():
    widget = tk.Tk()
    widget.withdraw()
    yield widget
    for job in widget.tk.call("after", "info"):
        widget.after_cancel(job)
    widget.destroy()


@pytest.mark.integration
def test_show_captures_once_before_native_nonactivating_show_and_lock(root):
    events = []
    class Native:
        def capture_screen_rgb(self, x, y, width, height):
            assert pill._window.state() == "withdrawn"
            events.append("capture")
            return bytes([210, 220, 230]) * width * height
        def show_without_activation(self, identity): events.append("show"); return True
        def prevent_click_activation(self, identity): events.append("lock"); return True
        def activate(self, identity): raise AssertionError("pill must not activate")
    pill = InlinePill(root, interaction_id="i", on_confirm=lambda _: None, on_cancel=lambda: None, native_window_surface=Native())
    try:
        pill.show()
        assert events == ["capture", "show", "lock"]
        pill.present(InlineDictationView("i", "awaiting", text="original"))
        pill.present(InlineDictationView("i", "recovery", text="original"))
        assert events == ["capture", "show", "lock"]
        assert not pill._window.bind("<Return>")
        assert not pill._window.bind("<Control-p>")
    finally:
        pill.close()


@pytest.mark.integration
def test_notification_has_no_reading_controls_and_copy_reuses_widgets_without_moving_pill(root):
    copies = []
    pill = InlinePill(root, interaction_id="i", on_confirm=lambda _: None, on_cancel=lambda: None, on_copy=lambda: copies.append(True))
    text = "original " * 90
    try:
        pill.show()
        view = InlineDictationView("i", "recovery", text=text)
        pill.present(view)
        root.update()
        bounds = pill._window.geometry()
        panel = pill._panel
        def descendants(widget):
            return [child for item in widget.winfo_children() for child in [item, *descendants(item)]]
        widgets = descendants(panel)
        assert not any(isinstance(widget, (tk.Text, tk.Scrollbar)) for widget in widgets)
        assert not hasattr(pill, "_text")
        assert pill._view.text == text
        pill._copy_button.invoke()
        assert copies == [True]
        pill.present(replace(view, copy_state="pending"))
        assert pill._copy_button.cget("state") == "disabled"
        pill.present(replace(view, copy_state="succeeded"))
        assert pill._copy_status.cget("text") == "已複製"
        assert pill._panel is panel
        assert pill._window.geometry() == bounds
    finally:
        pill.close()


@pytest.mark.integration
@pytest.mark.parametrize("scale", [1, 1.25, 1.5, 1.75, 2])
def test_notice_cards_fit_at_each_dpi_without_scrolling_or_clipping(root, scale):
    from ClipAI.core.voice import VoiceTransportFailure
    from ClipAI.core.models import PasteOutcome
    class Reader:
        def current(self): return DisplayMetrics(scale, 0, 0, 1600, 1000, 0, 0)
    pill = InlinePill(root, interaction_id="notice", on_confirm=lambda _: None, on_cancel=lambda: None, display_metrics=Reader(), placement="cursor")
    cases = [
        InlineDictationView("notice", "awaiting", text="full text "*200),
        InlineDictationView("notice", "awaiting", text="original", allow_refine=False),
        InlineDictationView("notice", "recovery", text="original"),
        InlineDictationView("notice", "recovery", text="original", paste_outcome=PasteOutcome("cleanup_failed", "dispatched_unconfirmed", "failed")),
        InlineDictationView("notice", "cancel_unconfirmed", text="original"),
        *[InlineDictationView("notice", "awaiting", text="original", capture_notice=reason) for reason in VoiceTransportFailure],
        *[InlineDictationView("notice", "closed", message="diagnostic", capture_notice=reason) for reason in VoiceTransportFailure],
    ]
    try:
        pill.show()
        bounds = pill._window.geometry()
        for view in cases:
            pill.present(view)
            root.update()
            panel = pill._panel
            assert panel is not None
            assert pill._window.geometry() == bounds
            children = [child for child in panel.winfo_children() if child.winfo_ismapped()]
            for child in children:
                assert child.winfo_y()+child.winfo_height() <= panel.winfo_height()
                if isinstance(child, tk.Label):
                    assert child.winfo_height() >= child.winfo_reqheight()
            for index, child in enumerate(children):
                for other in children[index+1:]:
                    assert child.winfo_y()+child.winfo_height() <= other.winfo_y() or other.winfo_y()+other.winfo_height() <= child.winfo_y()
    finally:
        pill.close()


@pytest.mark.integration
def test_idle_has_no_animation_and_click_lock_resets_only_on_phase_change(root):
    confirmations = []
    pill = InlinePill(root, interaction_id="i", on_confirm=confirmations.append, on_cancel=lambda: None)
    try:
        pill.show()
        awaiting = InlineDictationView("i", "awaiting", text="original")
        pill.present(awaiting)
        root.update()
        assert pill._frame_job is None
        layout = pill._layout
        x, y = layout.pill_x+round(142*layout.scale), layout.pill_y+round(18*layout.scale)
        for _ in range(2):
            pill._canvas.event_generate("<Button-1>", x=x, y=y)
        assert confirmations == [False]
        pill.present(replace(awaiting, message="same phase"))
        pill._canvas.event_generate("<Button-1>", x=x, y=y)
        assert confirmations == [False]
        pill.present(InlineDictationView("i", "finalizing", chosen="raw"))
        assert pill._frame_job is not None
        pill.present(awaiting)
        assert pill._frame_job is None
        pill._canvas.event_generate("<Button-1>", x=x, y=y)
        assert confirmations == [False, False]
    finally:
        pill.close()


@pytest.mark.integration
def test_popup_voice_indicator_renders_raster_shapes_and_animates_only_active_work(root):
    from ClipAI.ui.base_dialog import _VoiceWaveIndicator
    from ClipAI.ui.dialog_lifecycle import DialogLifecycle
    lifecycle = DialogLifecycle(root, owns_mainloop=False)
    indicator = _VoiceWaveIndicator(root, lifecycle=lifecycle, font_family="Microsoft JhengHei")
    try:
        indicator.update_state(word="語音", level=0, listening=False, silence=False, enabled=True, active=False, command=None, finishing=False)
        assert indicator._job is None
        assert {indicator.type(item) for item in indicator.find_all()} == {"image", "text"}
        indicator.update_state(word="整理", level=0, listening=False, silence=False, enabled=False, active=True, command=None, finishing=True)
        assert indicator._job is not None
        indicator.update_state(word="無聲", level=0, listening=True, silence=True, enabled=True, active=True, command=None, finishing=False)
        assert indicator._job is None
    finally:
        indicator.destroy()


@pytest.mark.integration
def test_each_new_pill_samples_display_dpi_and_keeps_frozen_bounds_during_copy(root):
    class Reader:
        scale = 1
        def current(self): return DisplayMetrics(self.scale, 0, 0, 1600, 1000, 1590, 990)
    reader = Reader()
    for scale in (1, 1.25, 1.5, 1.75, 2):
        reader.scale = scale
        pill = InlinePill(root, interaction_id="i", on_confirm=lambda _: None, on_cancel=lambda: None, display_metrics=reader)
        try:
            pill.show()
            layout = pill._layout
            assert pill._photo.width() == round(160*scale)
            assert pill._photo.height() == round(36*scale)
            pill.present(InlineDictationView("i", "recovery", text="full text", copy_state="failed"))
            root.update()
            assert pill._layout == layout
            assert pill._window.winfo_rootx()+pill._window.winfo_width() <= 1600-round(8*scale)
            assert pill._window.winfo_rooty()+pill._window.winfo_height() <= 1000-round(8*scale)
        finally:
            pill.close()


@pytest.mark.integration
def test_popup_raster_leaves_room_for_measured_word_and_formats_countdown(root):
    from ClipAI.ui.base_dialog import _VoiceWaveIndicator
    from ClipAI.ui.dialog_lifecycle import DialogLifecycle
    indicator = _VoiceWaveIndicator(root, lifecycle=DialogLifecycle(root, owns_mainloop=False), font_family="Microsoft JhengHei")
    try:
        indicator.update_state(word="聆聽", level=.8, listening=True, silence=False, enabled=True, active=True, command=None, countdown_seconds=90)
        labels = [item for item in indicator.find_all() if indicator.type(item) == "text"]
        assert indicator.itemcget(labels[0], "text") == "1:30"
        assert indicator.coords(labels[0])[0] < float(indicator.cget("width"))
        assert indicator._photo.width() == int(indicator.cget("width"))
    finally:
        indicator.destroy()


@pytest.mark.integration
def test_root_raster_resources_remain_invisible_and_close_idempotently(root):
    from ClipAI.ui.raster_resources import TkRasterResources
    initial = set(root.winfo_children())
    state = root.state()
    resources = TkRasterResources(root)
    created = set(root.winfo_children()) - initial
    assert len(created) == 1
    assert not next(iter(created)).winfo_ismapped()
    assert root.state() == state
    resources.close()
    resources.close()
    assert set(root.winfo_children()) == initial


@pytest.mark.integration
def test_native_noactivate_style_survives_first_mapping_and_render_events(root):
    import ctypes
    from ClipAI.platform.native_window import WindowsNativeWindowSurface
    native = WindowsNativeWindowSurface()
    pill = InlinePill(root, interaction_id="native-map", on_confirm=lambda _: None, on_cancel=lambda: None, native_window_surface=native)
    try:
        pill.show()
        root.update()
        child = pill._window.winfo_id()
        wrapper = ctypes.windll.user32.GetParent(child) or child
        assert ctypes.windll.user32.GetWindowLongW(wrapper, -20) & 0x08000000
    finally:
        pill.close()


@pytest.mark.integration
def test_pill_show_preserves_controlled_native_foreground_and_focused_entry(root):
    from ClipAI.platform.native_window import WindowsNativeWindowSurface
    native = WindowsNativeWindowSurface()
    entry = tk.Entry(root)
    entry.pack()
    root.deiconify()
    root.update()
    entry.focus_force()
    native.activate(root.winfo_id())
    root.update()
    assert native.owns_foreground(root.winfo_id())
    pill = InlinePill(root, interaction_id="i", on_confirm=lambda _: None, on_cancel=lambda: None, native_window_surface=native)
    try:
        pill.show()
        root.update()
        assert native.owns_foreground(root.winfo_id())
        assert root.focus_get() is entry
        pill.present(InlineDictationView("i", "awaiting", text="original"))
        root.update()
        assert native.owns_foreground(root.winfo_id())
        assert root.focus_get() is entry
    finally:
        pill.close()
        entry.destroy()
        root.withdraw()
