from ClipAI.core.models import ExternalWindowRef, PasteTarget
from ClipAI.core.state import CancellationToken
from ClipAI.platform.external_window import SystemExternalWindowActivator


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

    assert confirmation.state == "target_changed"
    assert "changed" in confirmation.message.lower()


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
