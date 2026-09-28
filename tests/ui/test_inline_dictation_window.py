"""Keyboard ownership at the inline dictation choice boundary."""

import tkinter as tk
import sys

import pytest
import customtkinter as ctk

from ClipAI.core.models import DisplayMetrics, PasteOutcome
from ClipAI.core.voice import VoiceCapabilityPhase, VoiceCapturePhase, VoiceProjection
from ClipAI.platform.native_window import WindowsNativeWindowSurface
from ClipAI.ui.inline_dictation import InlineDictationWindow, _clamp_inline_position


def test_inline_position_keeps_expanded_window_inside_work_area() -> None:
    metrics = DisplayMetrics(1.0, 0, 0, 1280, 720, 1270, 710)
    assert _clamp_inline_position(metrics, 400, 260) == (872, 452)
    assert _clamp_inline_position(DisplayMetrics(1.0, 0, 0, 1280, 720, 0, 0), 400, 260) == (14, 18)


@pytest.mark.integration
def test_inline_choice_and_recovery_reposition_after_expanding_near_screen_edge() -> None:
    root = tk.Tk()
    root.withdraw()
    width, height = root.winfo_screenwidth(), root.winfo_screenheight()

    class Reader:
        def current(self) -> DisplayMetrics:
            return DisplayMetrics(1.0, 0, 0, width, height, width - 2, height - 2)

    window = InlineDictationWindow(
        root, on_confirm=lambda _refine: None, on_cancel=lambda: None,
        display_metrics=Reader(),
    )
    try:
        window.show()
        for expand in (
            lambda: window.present_choice("recognized words " * 30),
            lambda: window.present_choice(
                "recognized words " * 30, allow_refine=False,
                message="Dictation refinement timed out. Original text is preserved. Choose raw paste, copy, or discard.",
            ),
            lambda: window.show_recovery("recognized words " * 30, "Paste unavailable"),
        ):
            expand()
            root.update()
            assert window._window.winfo_rootx() >= 8
            assert window._window.winfo_rooty() >= 8
            assert window._window.winfo_rootx() + window._window.winfo_width() <= width - 8
            assert window._window.winfo_rooty() + window._window.winfo_height() <= height - 8
    finally:
        window.close()
        root.destroy()


def _find_text_widget(parent: tk.Misc) -> tk.Text:
    for child in parent.winfo_children():
        if isinstance(child, tk.Text):
            return child
        try:
            return _find_text_widget(child)
        except LookupError:
            pass
    raise LookupError("No text widget found")


@pytest.mark.integration
def test_choice_activates_its_native_window_before_accepting_shortcuts() -> None:
    class NativeSurface:
        def __init__(self) -> None:
            self.activated_window_id: int | None = None

        def activate(self, window_id: int) -> bool:
            self.activated_window_id = window_id
            return True

    root = tk.Tk()
    root.withdraw()
    native = NativeSurface()
    confirmations: list[bool] = []
    try:
        for shortcut, refine in (("<Return>", False), ("<Control-p>", True)):
            window = InlineDictationWindow(
                root,
                on_confirm=confirmations.append,
                on_cancel=lambda: None,
                native_window_surface=native,
            )
            try:
                window.show()
                root.update()

                window.present_choice("recognized words")
                root.update()

                assert native.activated_window_id == window._window.winfo_id()
                assert root.focus_get() is window._window
                window._window.event_generate(shortcut)
                root.update()
                assert confirmations[-1] is refine
            finally:
                window.close()
    finally:
        root.destroy()


@pytest.mark.integration
def test_choice_keeps_the_complete_recognized_text_available() -> None:
    root = tk.Tk()
    root.withdraw()
    window = InlineDictationWindow(root, on_confirm=lambda _refine: None, on_cancel=lambda: None)
    text = "dictation " * 80
    try:
        window.show()
        window.present_choice(text)
        root.update()
        content = _find_text_widget(window._choice)
        assert content.get("1.0", "end-1c") == text
        assert any(isinstance(child, tk.Scrollbar) for child in content.master.winfo_children())
    finally:
        window.close()
        root.destroy()


@pytest.mark.integration
def test_minimal_status_requests_nonactivating_show_and_keeps_target_focus() -> None:
    class NativeSurface:
        def __init__(self) -> None:
            self.shown = []

        def show_without_activation(self, window_id: int) -> bool:
            self.shown.append(window_id)
            return True

    root = tk.Tk()
    entry = tk.Entry(root)
    entry.pack()
    root.update()
    entry.focus_force()
    root.update()
    native = NativeSurface()
    window = InlineDictationWindow(
        root, on_confirm=lambda _refine: None, on_cancel=lambda: None,
        native_window_surface=native, mode="minimal",
    )
    try:
        window.show()
        root.update()
        assert native.shown == [window._window.winfo_id()]
        assert root.focus_get() is entry
    finally:
        window.close()
        root.destroy()


@pytest.mark.integration
@pytest.mark.skipif(sys.platform != "win32", reason="requires a Windows foreground window")
def test_minimal_status_preserves_the_native_foreground_window() -> None:
    root = tk.Tk()
    target = tk.Entry(root)
    target.pack()
    native = WindowsNativeWindowSurface()
    window = InlineDictationWindow(
        root, on_confirm=lambda _refine: None, on_cancel=lambda: None,
        native_window_surface=native, mode="minimal",
    )
    try:
        root.update()
        root.lift()
        target.focus_force()
        root.update()
        activated = native.activate(root.winfo_id())
        root.update()
        if not native.owns_foreground(root.winfo_id()):
            foreground_present = bool(native._user32.GetForegroundWindow())
            pytest.skip(
                "controlled Tk target could not obtain native foreground; "
                f"activation_returned={activated}, foreground_present={foreground_present}"
            )

        window.show()
        root.update()
        assert native.owns_foreground(root.winfo_id())
    finally:
        window.close()
        root.destroy()


@pytest.mark.integration
def test_recovery_shows_complete_text_and_copy_pending_then_success() -> None:
    root = tk.Tk()
    root.withdraw()
    copied = []
    window = InlineDictationWindow(
        root, on_confirm=lambda _refine: None, on_cancel=lambda: None,
        on_copy=lambda: copied.append(True), mode="minimal",
    )
    text = "original " * 90
    try:
        window.show()
        window.show_recovery(text, "No paste target is available.")
        root.update()
        content = _find_text_widget(window._choice)
        assert content.get("1.0", "end-1c") == text
        window._copy_button.invoke()
        assert copied == [True]
        window.show_copy_state("pending")
        assert window._copy_button.cget("state") == "disabled"
        window.show_copy_state("succeeded")
        assert window._copy_button.cget("state") == "normal"
        assert window._copy_status.cget("text") == "已複製"
    finally:
        window.close()
        root.destroy()


@pytest.mark.integration
def test_refinement_failure_offers_raw_copy_and_discard_without_second_refinement() -> None:
    root = tk.Tk()
    root.withdraw()
    window = InlineDictationWindow(root, on_confirm=lambda _refine: None, on_cancel=lambda: None)
    try:
        window.show()
        window.present_choice("recognized words", allow_refine=False, message="Refinement failed. Choose raw paste or discard.")
        root.update()
        labels = [child.cget("text") for child in window._choice.winfo_children() if isinstance(child, tk.Label)]
        controls = next(child for child in window._choice.winfo_children() if isinstance(child, tk.Frame) and any(isinstance(item, ctk.CTkButton) for item in child.winfo_children()))
        buttons = {child.cget("text") for child in controls.winfo_children() if isinstance(child, ctk.CTkButton)}
        assert "Refinement failed. Choose raw paste or discard." in labels
        assert {"貼上原文", "複製", "丟棄"} <= buttons
        assert "潤飾後貼上" not in buttons
    finally:
        window.close()
        root.destroy()


@pytest.mark.integration
def test_refinement_surface_distinguishes_pending_from_admitted_work() -> None:
    root = tk.Tk()
    root.withdraw()
    window = InlineDictationWindow(root, on_confirm=lambda _refine: None, on_cancel=lambda: None)

    def words() -> set[str]:
        return {window._wave.itemcget(item, "text") for item in window._wave.find_all() if window._wave.type(item) == "text"}

    try:
        window.show()
        window.show_refinement_pending()
        root.update()
        assert "準備潤飾" in words()

        window.show_refining()
        root.update()
        assert "整理中" in words()
    finally:
        window.close()
        root.destroy()


@pytest.mark.integration
def test_capture_cancellation_stays_visible_with_pending_status() -> None:
    root = tk.Tk()
    root.withdraw()
    window = InlineDictationWindow(root, on_confirm=lambda _refine: None, on_cancel=lambda: None)
    try:
        window.show()
        window.update(VoiceProjection(
            VoiceCapabilityPhase.READY, "zh-TW",
            capture_phase=VoiceCapturePhase.CANCEL_REQUESTED,
        ))
        root.update()
        words = {
            window._wave.itemcget(item, "text")
            for item in window._wave.find_all()
            if window._wave.type(item) == "text"
        }
        assert "取消中" in words
        assert window._window.winfo_exists()
    finally:
        window.close()
        root.destroy()


@pytest.mark.integration
def test_capture_failure_notice_is_readable_and_no_longer_shows_active_work() -> None:
    root = tk.Tk()
    root.withdraw()
    window = InlineDictationWindow(root, on_confirm=lambda _refine: None, on_cancel=lambda: None)
    scheduled = []
    original_schedule = window._lifecycle.schedule
    try:
        window.show()
        window.update(VoiceProjection(
            VoiceCapabilityPhase.READY, "zh-TW",
            capture_phase=VoiceCapturePhase.FINALIZING,
        ))
        window._lifecycle.schedule = lambda delay, callback: scheduled.append((delay, callback))
        window.close(flash_failure=True, message="No speech was recognized. Try again.")
        root.update()
        words = {
            window._wave.itemcget(item, "text")
            for item in window._wave.find_all()
            if window._wave.type(item) == "text"
        }

        assert "未完成" in words
        assert "整理" not in words
        assert scheduled[0][0] == 3000
        assert window._window.winfo_exists()
    finally:
        window._lifecycle.schedule = original_schedule
        window._lifecycle.close()
        root.destroy()


@pytest.mark.integration
def test_unconfirmed_refinement_cancellation_keeps_complete_text_copyable() -> None:
    root = tk.Tk()
    root.withdraw()
    copied = []
    window = InlineDictationWindow(
        root, on_confirm=lambda _refine: None, on_cancel=lambda: None,
        on_copy=lambda: copied.append(True),
    )
    text = "complete original " * 45
    try:
        window.show()
        window.show_cancel_unconfirmed(text)
        root.update()
        content = _find_text_widget(window._choice)
        labels = [child.cget("text") for child in window._choice.winfo_children() if isinstance(child, tk.Label)]
        assert content.get("1.0", "end-1c") == text
        assert any("取消尚未確認" in label for label in labels)
        window._copy_button.invoke()
        assert copied == [True]
    finally:
        window.close()
        root.destroy()


@pytest.mark.integration
def test_confirm_shortcuts_only_emit_intent_on_choice_surface() -> None:
    root = tk.Tk()
    root.withdraw()
    confirmations: list[bool] = []
    window = InlineDictationWindow(root, on_confirm=confirmations.append, on_cancel=lambda: None)
    try:
        window.show()
        root.update()
        window.present_choice("recognized words")
        root.update()
        window._window.event_generate("<Return>")
        root.update()
        assert confirmations == [False]

        for show_nonchoice in (
            lambda: window.show_recovery("recognized words", "Target unavailable"),
            lambda: window.show_cancel_unconfirmed("recognized words"),
            lambda: window.show_paste_outcome(PasteOutcome("failed", "not_dispatched", "not_required"), "recognized words"),
        ):
            show_nonchoice()
            root.update()
            window._window.event_generate("<Return>")
            window._window.event_generate("<Control-p>")
            root.update()
            assert confirmations == [False]
    finally:
        window.close()
        root.destroy()
