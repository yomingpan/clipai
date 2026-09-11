from __future__ import annotations

from dataclasses import dataclass

from ClipAI.core.errors import InputError
from ClipAI.core.models import ExternalWindowRef, ImageContent, SelectionCaptureOutcome, SelectionSource
from ClipAI.platform.selection import SystemSelectionCaptureAdapter
from ClipAI.services.clipboard_transaction import ClipboardTransactionCoordinator
from ClipAI.services.selection_capture import SelectionCaptureCoordinator
from ClipAI.core.state import CancellationToken
import pytest


@dataclass(frozen=True)
class ClipboardSnapshot:
    text: str
    image: ImageContent | None = None


def reader(clipboard, **kwargs):
    copy_selection = kwargs.pop("copy_selection", None)
    modifier_is_pressed = kwargs.pop("modifier_is_pressed", lambda _modifier: False)
    return SelectionCaptureCoordinator(
        ClipboardTransactionCoordinator(clipboard),
        SystemSelectionCaptureAdapter(
            copy_selection=copy_selection,
            modifier_is_pressed=modifier_is_pressed,
        ),
        kwargs.pop("probe", Probe()),
        **kwargs,
    )


class Probe:
    def capture_source(self, target=None):
        return SelectionSource(target or ExternalWindowRef("hwnd:1", 42, 0), "hwnd:2")

    def source_is_current(self, source):
        return True

    def probe(self, source, cancellation):
        return SelectionCaptureOutcome(reason="uia_text_failed", selection_detected=True)


class Clipboard:
    def __init__(self, value: str, image: ImageContent | None = None) -> None:
        self.value = value
        self.image = image
        self.writes: list[str] = []
        self.sequence = 1
        self.external_after_sequence: str | None = None

    def read_text(self) -> str:
        return self.value

    def write_text(self, text: str) -> None:
        self.value = text
        self.writes.append(text)
        self.sequence += 1

    def write_transient_text(self, text: str) -> None:
        self.write_text(text)

    def snapshot(self) -> ClipboardSnapshot:
        return ClipboardSnapshot(self.value, self.image)

    def sequence_number(self) -> int:
        sequence = self.sequence
        if self.external_after_sequence is not None:
            self.value = self.external_after_sequence
            self.sequence += 1
            self.external_after_sequence = None
        return sequence

    def restore_if_unchanged(self, snapshot: ClipboardSnapshot, expected_sequence: int) -> bool:
        if self.sequence != expected_sequence:
            return False
        self.value = snapshot.text
        self.image = snapshot.image
        self.writes.append(snapshot.text)
        self.sequence += 1
        return True


def test_selection_capture_restores_original_clipboard() -> None:
    clipboard = Clipboard("original")

    def copy_selection() -> None:
        clipboard.value = "selected text"
        clipboard.sequence += 1

    selection = reader(clipboard, copy_selection=copy_selection, timeout_sec=0.01, poll_sec=0)
    assert selection.capture().text == "selected text"
    assert clipboard.value == "original"


def test_selection_capture_restores_original_non_text_content() -> None:
    image = ImageContent(b"png", "image/png")
    clipboard = Clipboard("", image)

    def copy_selection() -> None:
        clipboard.value = "selected text"
        clipboard.image = None
        clipboard.sequence += 1

    selection = reader(clipboard, copy_selection=copy_selection, timeout_sec=0.01, poll_sec=0)
    assert selection.capture().text == "selected text"
    assert clipboard.image == image


def test_selection_capture_waits_for_physical_hotkey_modifiers_to_be_released() -> None:
    clipboard = Clipboard("original")
    physical_modifiers = {"ctrl": True, "alt": True, "shift": False}
    checks = 0

    def modifier_is_pressed(modifier: str) -> bool:
        nonlocal checks
        checks += 1
        if checks > 3:
            physical_modifiers["ctrl"] = False
            physical_modifiers["alt"] = False
        return physical_modifiers[modifier]

    def copy_selection() -> None:
        if any(physical_modifiers.values()):
            return
        clipboard.value = "selected text"
        clipboard.sequence += 1

    selection = reader(
        clipboard,
        copy_selection=copy_selection,
        modifier_is_pressed=modifier_is_pressed,
        modifier_release_timeout_sec=0.01,
        timeout_sec=0.01,
        poll_sec=0,
    )

    assert selection.capture().text == "selected text"
    assert clipboard.value == "original"


def test_modifier_release_gate_precedes_source_check_and_probe() -> None:
    clipboard = Clipboard("original")
    events: list[str] = []
    pressed = iter([True, False, False, False, False, False])

    class OrderedProbe(Probe):
        def source_is_current(self, source):
            events.append("source")
            return True

        def probe(self, source, cancellation):
            events.append("probe")
            return SelectionCaptureOutcome(status="none", strategy="uia")

    selection = reader(
        clipboard,
        probe=OrderedProbe(),
        modifier_is_pressed=lambda _modifier: events.append("modifier") or next(pressed),
        modifier_release_timeout_sec=0.1,
        poll_sec=0,
    )

    assert selection.capture().status == "none"
    assert events[:6] == ["modifier"] * 6
    assert events[6:] == ["source", "probe", "source"]


def test_modifier_timeout_never_checks_source_or_probes() -> None:
    clipboard = Clipboard("original")

    class RejectProbe(Probe):
        def source_is_current(self, source):
            pytest.fail("source must not be checked while a hotkey modifier is held")

        def probe(self, source, cancellation):
            pytest.fail("probe must not run while a hotkey modifier is held")

    outcome = reader(
        clipboard,
        probe=RejectProbe(),
        modifier_is_pressed=lambda modifier: modifier == "ctrl",
        modifier_release_timeout_sec=0,
        poll_sec=0,
    ).capture()

    assert (outcome.status, outcome.reason) == ("unknown", "modifier_timeout")
    assert clipboard.writes == []


def test_selection_capture_does_not_copy_or_mutate_clipboard_when_modifiers_stay_pressed() -> None:
    clipboard = Clipboard("original")
    copy_calls = 0

    def copy_selection() -> None:
        nonlocal copy_calls
        copy_calls += 1

    selection = reader(
        clipboard,
        copy_selection=copy_selection,
        modifier_is_pressed=lambda modifier: modifier == "alt",
        modifier_release_timeout_sec=0,
        timeout_sec=0.01,
        poll_sec=0,
    )

    assert selection.capture().text == ""
    assert copy_calls == 0
    assert clipboard.value == "original"
    assert clipboard.writes == []


def test_selection_capture_does_not_overwrite_later_external_clipboard_update() -> None:
    clipboard = Clipboard("original")

    def copy_selection() -> None:
        clipboard.value = "selected text"
        clipboard.sequence += 1
        clipboard.external_after_sequence = "external update"

    selection = reader(clipboard, copy_selection=copy_selection, timeout_sec=0.01, poll_sec=0)
    assert selection.capture().text == ""
    assert clipboard.value == "external update"


def test_selection_capture_failure_falls_back_safely() -> None:
    clipboard = Clipboard("original")
    selection = reader(
        clipboard,
        copy_selection=lambda: (_ for _ in ()).throw(RuntimeError("copy failed")),
        timeout_sec=0.01,
        poll_sec=0,
    )
    assert selection.capture().text == ""
    assert clipboard.value == "original"


def test_selection_capture_snapshot_failure_falls_back_safely() -> None:
    clipboard = Clipboard("original")

    def fail_snapshot() -> ClipboardSnapshot:
        raise InputError("Clipboard format 49804 could not be rendered for preservation.")

    clipboard.snapshot = fail_snapshot  # type: ignore[method-assign]
    selection = reader(clipboard, timeout_sec=0.01, poll_sec=0)

    assert selection.capture().text == ""
    assert clipboard.value == "original"


def test_selection_capture_observes_operation_cancellation() -> None:
    clipboard = Clipboard("original")
    token = CancellationToken()
    token.cancel()
    selection = reader(
        clipboard,
        copy_selection=lambda: None,
        modifier_is_pressed=lambda _modifier: True,
        modifier_release_timeout_sec=1,
        timeout_sec=1,
        poll_sec=0,
    )
    assert selection.capture(token).text == ""
    assert clipboard.writes == []


@pytest.mark.parametrize("outcome", [
    SelectionCaptureOutcome("  selected\n\t", "selected", strategy="uia"),
    SelectionCaptureOutcome(status="none", strategy="uia"),
    SelectionCaptureOutcome(reason="uia_unsupported", strategy="uia"),
    SelectionCaptureOutcome(reason="uia_timeout", strategy="uia"),
])
def test_native_probe_preserves_all_states_without_touching_clipboard(outcome):
    clipboard = Clipboard("old text")
    probe = Probe()
    probe.probe = lambda source, cancellation: outcome
    selection = reader(clipboard, probe=probe, modifier_is_pressed=lambda _: False)
    assert selection.capture() == outcome
    assert clipboard.writes == []


def test_copy_timeout_is_unknown_never_confirmed_no_selection():
    clipboard = Clipboard("old text")
    result = reader(clipboard, copy_selection=lambda: None, timeout_sec=0).capture()
    assert result.status == "unknown"
    assert result.reason == "copy_timeout"
    assert clipboard.value == "old text"


@pytest.mark.parametrize("selected", [True, False])
def test_verified_selection_only_copy_reaches_speech_without_using_old_clipboard(selected):
    from ClipAI.services.speech_coordinator import SpeechCoordinator, SpeechVoiceSelector
    from ClipAI.core.errors import SelectionUnavailableError

    clipboard = Clipboard("old text must never be spoken")
    probe = Probe()
    probe.probe = lambda *args: SelectionCaptureOutcome(copy_selection_only=True)
    spoken = []

    def copy():
        if selected:
            clipboard.write_text("She places a high value on open discussions.")

    class Speech:
        def speak(self, request):
            spoken.append(request.text)

        def stop(self):
            pass

    coordinator = SpeechCoordinator(
        clipboard=clipboard,
        selection_reader=reader(clipboard, probe=probe, copy_selection=copy, timeout_sec=.01, poll_sec=0),
        speech=Speech(), voice_selector=SpeechVoiceSelector("en-test"),
    )
    job = coordinator.create_job(clipboard_only=False)
    if selected:
        job.run()
        assert spoken == ["She places a high value on open discussions."]
    else:
        with pytest.raises(SelectionUnavailableError):
            job.run()
        assert spoken == []
    assert clipboard.value == "old text must never be spoken"


def test_verified_copy_capability_does_not_override_source_change():
    clipboard = Clipboard("original")
    probe = Probe()
    current = [True]

    def changed(*args):
        current[0] = False
        return SelectionCaptureOutcome(copy_selection_only=True)

    probe.probe = changed
    probe.source_is_current = lambda _: current[0]
    result = reader(clipboard, probe=probe).capture()
    assert result.reason == "source_changed"
    assert clipboard.writes == []


def test_focus_restoration_rebaselines_same_window_before_staleness_check():
    clipboard = Clipboard("original")
    original = SelectionSource(ExternalWindowRef("hwnd:1", 42, 0), "hwnd:2")
    restored = SelectionSource(original.window, "hwnd:3")
    events = []

    class RestoringProbe(Probe):
        def capture_source(self, target=None):
            events.append(("capture", target))
            return original if target is None else restored

        def source_is_current(self, source):
            events.append(("current", source))
            return source == original if len([event for event in events if event[0] == "current"]) == 1 else source == restored

        def probe(self, source, cancellation):
            events.append(("probe", source))
            return SelectionCaptureOutcome(
                "restored selection",
                "selected",
                strategy="uia",
                selection_detected=True,
                focus_restored=True,
            )

    outcome = reader(clipboard, probe=RestoringProbe()).capture()

    assert outcome.text == "restored selection"
    assert events == [
        ("capture", None),
        ("current", original),
        ("probe", original),
        ("capture", original.window),
        ("current", restored),
    ]


def test_focus_restoration_to_different_window_discards_selected_text():
    clipboard = Clipboard("original")
    original = SelectionSource(ExternalWindowRef("hwnd:1", 42, 0), "hwnd:2")
    wrong = SelectionSource(ExternalWindowRef("hwnd:9", 99, 0), "hwnd:a")

    class RestoringProbe(Probe):
        def capture_source(self, target=None):
            return original if target is None else wrong

        def probe(self, source, cancellation):
            return SelectionCaptureOutcome(
                "wrong source text",
                "selected",
                strategy="uia",
                selection_detected=True,
                focus_restored=True,
            )

    outcome = reader(clipboard, probe=RestoringProbe()).capture()

    assert (outcome.status, outcome.reason, outcome.text) == ("unknown", "source_changed", "")


def test_focus_restored_capability_must_be_boolean():
    with pytest.raises(ValueError, match="focus_restored"):
        SelectionCaptureOutcome(focus_restored="true")  # type: ignore[arg-type]


def test_source_is_frozen_before_panel_focus_changes():
    clipboard = Clipboard("old text")
    probe = Probe()
    selection = reader(clipboard, probe=probe)
    request = selection.begin_capture()
    probe.capture_source = lambda target: pytest.fail("must not replace bound source")
    probe.source_is_current = lambda source: False
    probe.probe = lambda *args: pytest.fail("must not read from changed source")
    result = selection.capture(request=request)
    assert result.status == "unknown"
    assert result.reason == "source_changed"
    assert clipboard.writes == []


def test_late_native_success_is_discarded_after_cancellation():
    clipboard = Clipboard("old text")
    token = CancellationToken()
    probe = Probe()
    def capture(source, cancellation):
        cancellation.cancel()
        return SelectionCaptureOutcome("late text", "selected")
    probe.probe = capture
    result = reader(clipboard, probe=probe).capture(token)
    assert result.status == "cancelled"
    assert result.text == ""
    assert clipboard.writes == []


def test_selection_diagnostics_never_include_source_text(caplog):
    clipboard = Clipboard("private clipboard")
    probe = Probe()
    probe.probe = lambda *args: SelectionCaptureOutcome(
        reason="selection_only_copy_available",
        strategy="uia",
        copy_selection_only=True,
        focus_restored=True,
    )
    with caplog.at_level("INFO", logger="clipai.selection"):
        reader(
            clipboard,
            probe=probe,
            copy_selection=lambda: clipboard.write_text("private selected text"),
            timeout_sec=0.001,
            poll_sec=0,
        ).capture()
    assert "status=selected" in caplog.text
    assert "focus_restored=True" in caplog.text
    assert "private selected text" not in caplog.text
    assert "private clipboard" not in caplog.text
