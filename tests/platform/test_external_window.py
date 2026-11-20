import logging

import pytest

from ClipAI.core.errors import CancelledError
from ClipAI.core.models import ExternalWindowRef, ExternalWindowWaitPolicy, PasteTarget
from ClipAI.core.state import CancellationToken
from ClipAI.platform.external_window import SystemExternalWindowActivator


@pytest.mark.parametrize("phase", ["activate", "confirm"])
@pytest.mark.parametrize("return_at, expected", [(0, "activated"), (0.48, "activated"), (0.54, "activated"), (2.8, "activated"), (4, "target_focus_timeout")])
def test_focus_wait_budget_and_real_wait_notice(monkeypatch, phase, return_at, expected):
    clock = [0.0]
    notices = []
    requests = []
    target = ExternalWindowRef("hwnd:2a", 42, 7)
    monkeypatch.setattr("ClipAI.platform.external_window.time.monotonic", lambda: clock[0])
    def wait(seconds):
        clock[0] += seconds
    activator = SystemExternalWindowActivator(
        modifier_is_pressed=lambda _: False,
        target_is_valid=lambda candidate: candidate == target,
        target_is_foreground=lambda candidate: candidate == target and clock[0] >= return_at,
        activate_target=lambda candidate: requests.append(candidate) or True,
        wait=wait,
    )
    outcome = getattr(activator, phase)(
        target, CancellationToken(), wait_policy=ExternalWindowWaitPolicy(),
        on_waiting=lambda: notices.append(clock[0]),
    )
    assert outcome.state == expected
    assert clock[0] == pytest.approx(min(return_at, 3), abs=0.021)
    assert len(notices) == (1 if return_at > 0.5 else 0)
    if notices:
        assert notices[0] == pytest.approx(0.5, abs=0.021)
    assert all(candidate == target for candidate in requests)


@pytest.mark.parametrize("phase", ["activate", "confirm"])
@pytest.mark.parametrize("stop", ["cancel", "invalid"])
def test_slow_focus_wait_stops_on_cancellation_or_invalid_source(monkeypatch, phase, stop):
    clock = [0.0]
    token = CancellationToken()
    notices = []
    monkeypatch.setattr("ClipAI.platform.external_window.time.monotonic", lambda: clock[0])
    def wait(seconds):
        clock[0] += seconds
        if stop == "cancel" and clock[0] >= 0.8:
            token.cancel()
    activator = SystemExternalWindowActivator(
        modifier_is_pressed=lambda _: False,
        target_is_valid=lambda _: stop != "invalid" or clock[0] < 0.8,
        target_is_foreground=lambda _: False,
        activate_target=lambda _: True,
        wait=wait,
    )
    def run():
        return getattr(activator, phase)(
            ExternalWindowRef("hwnd:2a", 42, 7), token,
            wait_policy=ExternalWindowWaitPolicy(), on_waiting=lambda: notices.append(clock[0]),
        )
    if stop == "cancel":
        with pytest.raises(CancelledError):
            run()
    else:
        assert run().state == "target_changed"
    assert clock[0] == pytest.approx(0.8, abs=0.021)
    assert len(notices) == 1


def test_already_foreground_selection_source_does_not_wait_for_alt_release():
    target = ExternalWindowRef("hwnd:2a", 42, 7)
    activator = SystemExternalWindowActivator(
        modifier_is_pressed=lambda _: True,
        target_is_valid=lambda candidate: candidate == target,
        target_is_foreground=lambda candidate: candidate == target,
        activate_target=lambda _: pytest.fail("must preserve existing focus"),
        wait=lambda _: pytest.fail("UIA does not need modifier release"),
    )
    assert activator.activate(target, CancellationToken()).activated


def test_external_window_activator_validates_and_confirms_captured_target() -> None:
    target = ExternalWindowRef("hwnd:2a", 42, 7)
    foreground = {"value": False}

    def activate(candidate: ExternalWindowRef) -> bool:
        assert candidate == target
        foreground["value"] = True
        return True

    activator = SystemExternalWindowActivator(
        modifier_is_pressed=lambda _modifier: False,
        target_confirmation_timeout_sec=0,
        target_is_valid=lambda candidate: candidate == target,
        activate_target=activate,
        target_is_foreground=lambda candidate: candidate == target and foreground["value"],
        wait=lambda _seconds: None,
    )

    outcome = activator.activate(target, CancellationToken())

    assert outcome.state == "activated"
    assert outcome.message == ""


def test_external_window_activator_fails_closed_when_captured_target_is_gone() -> None:
    target = ExternalWindowRef("hwnd:2a", 42, 7)
    activation_requests = []
    activator = SystemExternalWindowActivator(
        modifier_is_pressed=lambda _modifier: False,
        target_is_valid=lambda _candidate: False,
        activate_target=lambda candidate: activation_requests.append(candidate) or True,
        target_is_foreground=lambda _candidate: False,
        wait=lambda _seconds: None,
    )

    outcome = activator.activate(target, CancellationToken())

    assert outcome.state == "target_gone"
    assert outcome.activated is False
    assert activation_requests == []


def test_external_window_activator_reports_focus_refusal_without_substitution() -> None:
    target = ExternalWindowRef("hwnd:2a", 42, 7)
    activator = SystemExternalWindowActivator(
        modifier_is_pressed=lambda _modifier: False,
        target_activation_timeout_sec=0,
        target_is_valid=lambda candidate: candidate == target,
        activate_target=lambda _candidate: False,
        target_is_foreground=lambda _candidate: False,
        wait=lambda _seconds: None,
    )

    outcome = activator.activate(target, CancellationToken())

    assert outcome.state == "target_refused_focus"
    assert "original window" in outcome.message.lower()


def test_external_window_activator_retries_a_transient_initial_focus_refusal(
    monkeypatch,
) -> None:
    target = ExternalWindowRef("hwnd:2a", 42, 7)
    attempts = 0
    clock = {"now": 0.0}

    def activate(_candidate: ExternalWindowRef) -> bool:
        nonlocal attempts
        attempts += 1
        return attempts >= 2

    activator = SystemExternalWindowActivator(
        modifier_is_pressed=lambda _modifier: False,
        target_activation_timeout_sec=0.05,
        poll_sec=0.01,
        wait=lambda seconds: clock.__setitem__("now", clock["now"] + seconds),
        target_is_valid=lambda candidate: candidate == target,
        activate_target=activate,
        target_is_foreground=(
            lambda candidate: candidate == target and attempts >= 2
        ),
    )
    monkeypatch.setattr(
        "ClipAI.platform.external_window.time.monotonic",
        lambda: clock["now"],
    )

    outcome = activator.activate(target, CancellationToken())

    assert outcome.state == "activated"
    assert attempts == 2


def test_external_window_activator_retries_an_accepted_focus_request(monkeypatch) -> None:
    target = ExternalWindowRef("hwnd:2a", 42, 7)
    attempts = 0
    clock = {"now": 0.0}

    def activate(_candidate: ExternalWindowRef) -> bool:
        nonlocal attempts
        attempts += 1
        return True

    def wait(seconds: float) -> None:
        clock["now"] += seconds

    activator = SystemExternalWindowActivator(
        modifier_is_pressed=lambda _modifier: False,
        target_activation_timeout_sec=0.05,
        poll_sec=0.01,
        wait=wait,
        target_is_valid=lambda candidate: candidate == target,
        activate_target=activate,
        target_is_foreground=lambda candidate: candidate == target and attempts >= 2,
    )

    monkeypatch.setattr(
        "ClipAI.platform.external_window.time.monotonic",
        lambda: clock["now"],
    )

    outcome = activator.activate(target, CancellationToken())

    assert outcome.state == "activated"
    assert attempts == 2


def test_external_window_activator_does_not_retry_past_its_deadline(monkeypatch) -> None:
    target = ExternalWindowRef("hwnd:2a", 42, 7)
    attempts = 0
    clock = {"now": 0.0}

    def activate(_candidate: ExternalWindowRef) -> bool:
        nonlocal attempts
        attempts += 1
        return True

    activator = SystemExternalWindowActivator(
        modifier_is_pressed=lambda _modifier: False,
        target_activation_timeout_sec=0.05,
        poll_sec=0.05,
        wait=lambda seconds: clock.__setitem__("now", clock["now"] + seconds),
        target_is_valid=lambda candidate: candidate == target,
        activate_target=activate,
        target_is_foreground=lambda _candidate: False,
    )
    monkeypatch.setattr(
        "ClipAI.platform.external_window.time.monotonic",
        lambda: clock["now"],
    )

    outcome = activator.activate(target, CancellationToken())

    assert outcome.state == "target_focus_timeout"
    assert attempts == 1


def test_external_window_confirmation_rejects_focus_lost_after_capture() -> None:
    target = ExternalWindowRef("hwnd:2a", 42, 7)
    foreground = {"value": True}
    activator = SystemExternalWindowActivator(
        modifier_is_pressed=lambda _modifier: False,
        target_confirmation_timeout_sec=0,
        target_is_valid=lambda candidate: candidate == target,
        activate_target=lambda _candidate: True,
        target_is_foreground=lambda candidate: candidate == target and foreground["value"],
        wait=lambda _seconds: None,
    )
    assert activator.activate(target, CancellationToken()).activated is True

    foreground["value"] = False
    confirmation = activator.confirm(target)

    assert confirmation.state == "target_focus_timeout"
    assert "in time" in confirmation.message.lower()


def test_external_window_confirmation_logs_safe_foreground_diagnostics(
    caplog,
) -> None:
    target = ExternalWindowRef("hwnd:2a", 42, 7)
    activator = SystemExternalWindowActivator(
        modifier_is_pressed=lambda _modifier: False,
        target_confirmation_timeout_sec=0,
        target_is_valid=lambda candidate: candidate == target,
        activate_target=lambda _candidate: True,
        target_is_foreground=lambda _candidate: False,
        wait=lambda _seconds: None,
    )
    caplog.set_level(logging.INFO, logger="clipai.external_window")

    confirmation = activator.confirm(target, CancellationToken())

    assert confirmation.state == "target_focus_timeout"
    trace = caplog.text
    assert "phase=confirmation" in trace
    assert "state=target_focus_timeout" in trace
    assert "target_window=hwnd:2a" in trace
    assert "target_process_id=42" in trace
    assert "foreground_owner=" in trace


def test_external_window_confirmation_waits_for_transient_focus_to_return(
    monkeypatch,
) -> None:
    target = ExternalWindowRef("hwnd:2a", 42, 7)
    clock = {"now": 0.0}
    foreground = iter((False, False, True))
    activator = SystemExternalWindowActivator(
        modifier_is_pressed=lambda _modifier: False,
        target_confirmation_timeout_sec=0.05,
        poll_sec=0.01,
        wait=lambda seconds: clock.__setitem__("now", clock["now"] + seconds),
        target_is_valid=lambda candidate: candidate == target,
        activate_target=lambda _candidate: True,
        target_is_foreground=lambda candidate: (
            candidate == target and next(foreground)
        ),
    )
    monkeypatch.setattr(
        "ClipAI.platform.external_window.time.monotonic",
        lambda: clock["now"],
    )

    confirmation = activator.confirm(target, CancellationToken())

    assert confirmation.state == "activated"


def test_external_window_confirmation_observes_cancellation_while_waiting() -> None:
    target = ExternalWindowRef("hwnd:2a", 42, 7)
    cancellation = CancellationToken()
    activator = SystemExternalWindowActivator(
        modifier_is_pressed=lambda _modifier: False,
        target_confirmation_timeout_sec=1,
        target_is_valid=lambda candidate: candidate == target,
        activate_target=lambda _candidate: True,
        target_is_foreground=lambda _candidate: False,
        wait=lambda _seconds: cancellation.cancel(),
    )

    with pytest.raises(CancelledError):
        activator.confirm(target, cancellation)


def test_external_window_activator_prepares_paste_target_through_the_same_seam() -> None:
    target = PasteTarget("hwnd:2a", 42, "Notepad", "Untitled", 7)
    activator = SystemExternalWindowActivator(
        modifier_is_pressed=lambda _modifier: False,
        target_is_valid=lambda candidate: candidate == target,
        activate_target=lambda candidate: candidate == target,
        target_is_foreground=lambda candidate: candidate == target,
        wait=lambda _seconds: None,
    )

    outcome = activator.activate(target, CancellationToken())

    assert outcome.state == "activated"
