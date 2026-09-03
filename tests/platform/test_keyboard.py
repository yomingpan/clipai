from __future__ import annotations

import logging

import pytest

from ClipAI.core.errors import PasteFailure
from ClipAI.platform.keyboard import SystemKeyboardOutput
from ClipAI.core.models import PasteTarget
from ClipAI.core.state import CancellationToken


TARGET = PasteTarget("hwnd:10", 42, "Notepad", "Untitled", 1)


def test_paste_waits_for_physical_modifiers_to_be_released() -> None:
    ctrl_pressed = [True]
    waits: list[float] = []
    pasted: list[str] = []

    def modifier_is_pressed(modifier: str) -> bool:
        return modifier == "ctrl" and ctrl_pressed[0]

    def wait(delay: float) -> None:
        waits.append(delay)
        ctrl_pressed[0] = False

    keyboard = SystemKeyboardOutput(
        modifier_is_pressed=modifier_is_pressed,
        paste_settle_sec=0,
        poll_sec=0.02,
        wait=wait,
        paste_shortcut=lambda: pasted.append("paste"),
        target_is_valid=lambda target: target == TARGET,
        activate_target=lambda target: target == TARGET,
        target_is_foreground=lambda target: target == TARGET,
    )

    receipt = keyboard.dispatch("paste-1", TARGET, CancellationToken())

    assert waits == [0.02]
    assert pasted == ["paste"]
    assert receipt.state == "dispatched_unconfirmed"


def test_paste_fails_without_injecting_when_modifiers_do_not_release() -> None:
    pasted: list[str] = []
    keyboard = SystemKeyboardOutput(
        modifier_is_pressed=lambda _modifier: True,
        modifier_release_timeout_sec=0,
        wait=lambda _delay: None,
        paste_shortcut=lambda: pasted.append("paste"),
        target_is_valid=lambda _target: True,
        activate_target=lambda _target: True,
        target_is_foreground=lambda _target: True,
    )

    with pytest.raises(PasteFailure) as raised:
        keyboard.dispatch("paste-1", TARGET, CancellationToken())

    assert raised.value.reason == "modifiers_held"
    assert pasted == []


def test_paste_rejects_invalid_target_without_injecting() -> None:
    pasted: list[str] = []
    keyboard = SystemKeyboardOutput(
        modifier_is_pressed=lambda _modifier: False,
        paste_shortcut=lambda: pasted.append("paste"),
        target_is_valid=lambda _target: False,
        activate_target=lambda _target: True,
        target_is_foreground=lambda _target: True,
    )

    with pytest.raises(PasteFailure) as raised:
        keyboard.dispatch("paste-1", TARGET, CancellationToken())

    assert raised.value.reason == "target_gone"
    assert pasted == []


def test_paste_cancellation_is_checked_immediately_before_dispatch() -> None:
    cancellation = CancellationToken()
    foreground_checks = 0
    pasted: list[str] = []

    def foreground(_target) -> bool:
        nonlocal foreground_checks
        foreground_checks += 1
        if foreground_checks == 2:
            cancellation.cancel()
        return True

    keyboard = SystemKeyboardOutput(
        modifier_is_pressed=lambda _modifier: False,
        paste_shortcut=lambda: pasted.append("paste"),
        target_is_valid=lambda _target: True,
        activate_target=lambda _target: True,
        target_is_foreground=foreground,
    )

    with pytest.raises(RuntimeError, match="cancelled"):
        keyboard.dispatch("paste-1", TARGET, cancellation)

    assert pasted == []


def test_paste_revalidates_target_and_foreground_at_commit_gate() -> None:
    validity = iter((True, False))
    pasted: list[str] = []
    keyboard = SystemKeyboardOutput(
        modifier_is_pressed=lambda _modifier: False,
        paste_shortcut=lambda: pasted.append("paste"),
        target_is_valid=lambda _target: next(validity),
        activate_target=lambda _target: True,
        target_is_foreground=lambda _target: True,
    )

    with pytest.raises(PasteFailure) as raised:
        keyboard.dispatch("paste-1", TARGET, CancellationToken())

    assert raised.value.reason == "target_changed"
    assert pasted == []


def test_paste_reports_target_refused_focus_at_activation_gate() -> None:
    keyboard = SystemKeyboardOutput(
        modifier_is_pressed=lambda _modifier: False,
        target_is_valid=lambda _target: True,
        activate_target=lambda _target: False,
        target_is_foreground=lambda _target: False,
    )

    with pytest.raises(PasteFailure) as raised:
        keyboard.dispatch("paste-1", TARGET, CancellationToken())

    assert raised.value.reason == "target_refused_focus"


def test_paste_reports_target_focus_timeout_after_accepted_activation() -> None:
    keyboard = SystemKeyboardOutput(
        modifier_is_pressed=lambda _modifier: False,
        target_activation_timeout_sec=0,
        wait=lambda _delay: None,
        target_is_valid=lambda _target: True,
        activate_target=lambda _target: True,
        target_is_foreground=lambda _target: False,
    )

    with pytest.raises(PasteFailure) as raised:
        keyboard.dispatch("paste-1", TARGET, CancellationToken())

    assert raised.value.reason == "target_focus_timeout"


def test_input_injection_error_after_commit_is_reported_as_unconfirmed_dispatch() -> None:
    keyboard = SystemKeyboardOutput(
        modifier_is_pressed=lambda _modifier: False,
        paste_shortcut=lambda: (_ for _ in ()).throw(OSError("injection failed")),
        target_is_valid=lambda _target: True,
        activate_target=lambda _target: True,
        target_is_foreground=lambda _target: True,
    )

    receipt = keyboard.dispatch("paste-1", TARGET, CancellationToken())

    assert receipt.state == "dispatched_unconfirmed"
    assert "after the Paste Dispatch point" in receipt.detail


def test_paste_dispatch_trace_records_commit_boundaries_without_target_metadata(caplog) -> None:
    keyboard = SystemKeyboardOutput(
        modifier_is_pressed=lambda _modifier: False,
        paste_settle_sec=0,
        paste_shortcut=lambda: None,
        target_is_valid=lambda _target: True,
        activate_target=lambda _target: True,
        target_is_foreground=lambda _target: True,
    )
    caplog.set_level(logging.INFO, logger="clipai.keyboard_paste")

    keyboard.dispatch("paste-trace", TARGET, CancellationToken())

    trace = caplog.text
    assert "operation_id=paste-trace" in trace
    assert "stage=activation" in trace
    assert "stage=shortcut_started" in trace
    assert "stage=shortcut_returned" in trace
    assert "stage=settled" in trace
    assert "target_window=hwnd:10" in trace
    assert "target_process_id=42" in trace
    assert "Notepad" not in trace
    assert "Untitled" not in trace
