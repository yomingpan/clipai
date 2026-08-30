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
        target_is_valid=lambda candidate: candidate == target,
        activate_target=lambda _candidate: False,
        target_is_foreground=lambda _candidate: False,
        wait=lambda _seconds: None,
    )

    outcome = activator.activate(target, CancellationToken())

    assert outcome.state == "target_refused_focus"
    assert "original window" in outcome.message.lower()


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
