from __future__ import annotations

import pytest

from ClipAI.services.speech_coordinator import SpeechCoordinator, SpeechVoiceSelector


class Reader:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = 0

    def read_text(self) -> str:
        self.calls += 1
        return self.text


class Speech:
    def __init__(self, error: BaseException | None = None) -> None:
        self.requests = []
        self.stops = 0
        self.error = error

    def speak(self, request) -> None:
        self.requests.append(request)
        if self.error is not None:
            raise self.error

    def stop(self) -> None:
        self.stops += 1


class Handle:
    def __init__(self) -> None:
        self.outcomes: list[str] = []

    def succeed(self) -> None:
        self.outcomes.append("success")

    def fail(self) -> None:
        self.outcomes.append("error")

    def cancel(self) -> None:
        self.outcomes.append("cancel")


class Tracker:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, Handle]] = []

    def start(self, operation_id: str, kind: str) -> Handle:
        handle = Handle()
        self.calls.append((operation_id, kind, handle))
        return handle


def make_coordinator(*, clipboard="clipboard", selection="selected", speech=None, tracker=None, speech_rate=None):
    clipboard_reader = Reader(clipboard)
    selection_reader = Reader(selection)
    speech = speech or Speech()
    tracker = tracker or Tracker()
    coordinator = SpeechCoordinator(
        clipboard=clipboard_reader,
        selection_reader=selection_reader,
        speech=speech,
        voice_selector=SpeechVoiceSelector("en-GB-TestVoice"),
        operation_tracker=tracker,
        speech_rate=speech_rate,
    )
    return coordinator, clipboard_reader, selection_reader, speech, tracker


def test_selection_first_and_configured_english_voice() -> None:
    coordinator, clipboard, selection, speech, tracker = make_coordinator()
    job = coordinator.create_job(clipboard_only=False)
    job.run()
    assert selection.calls == 1
    assert clipboard.calls == 0
    assert speech.requests[0].text == "selected"
    assert speech.requests[0].voice_override == "en-GB-TestVoice"
    assert tracker.calls == []


def test_clipboard_only_does_not_read_selection_and_cjk_uses_default_voice() -> None:
    coordinator, clipboard, selection, speech, _tracker = make_coordinator(clipboard="你好", selection="wrong")
    coordinator.create_job(clipboard_only=True).run()
    assert selection.calls == 0
    assert clipboard.calls == 1
    assert speech.requests[0].voice_override is None


@pytest.mark.parametrize(
    "text",
    (
        "これは日本語です。",
        "ひらがなだけ",
        "カタカナ",
        "ﾊﾝｶｸｶﾀｶﾅ",
    ),
)
def test_japanese_text_uses_configured_japanese_voice(text: str) -> None:
    speech = Speech()
    coordinator = SpeechCoordinator(
        clipboard=Reader(""),
        selection_reader=Reader(""),
        speech=speech,
        voice_selector=SpeechVoiceSelector(
            "en-GB-TestVoice",
            japanese_voice="ja-JP-NanamiNeural",
        ),
    )

    coordinator.create_text_job(
        operation_id="japanese-speech",
        workflow_id="workflow",
        text=text,
    ).run()

    assert speech.requests[0].voice_override == "ja-JP-NanamiNeural"


def test_empty_preprocessed_text_is_successful_noop() -> None:
    coordinator, _clipboard, _selection, speech, tracker = make_coordinator(clipboard="```py\npass\n```", selection="")
    coordinator.create_job(clipboard_only=False).run()
    assert speech.requests == []
    assert tracker.calls == []


def test_new_job_cancels_old_job_without_old_completion_overwriting_new() -> None:
    coordinator, _clipboard, _selection, _speech, tracker = make_coordinator()
    old_job = coordinator.create_job(clipboard_only=False)
    new_job = coordinator.create_job(clipboard_only=False)
    old_job.run()
    new_job.run()
    assert old_job.operation_id != new_job.operation_id
    assert tracker.calls == []


def test_each_trigger_reads_the_current_selection_again() -> None:
    coordinator, _clipboard, selection, speech, _tracker = make_coordinator()
    for value in ("first", "second", "third"):
        selection.text = value
        coordinator.create_job(clipboard_only=False).run()
    assert [request.text for request in speech.requests] == ["first", "second", "third"]
    assert selection.calls == 3


def test_selection_is_captured_when_job_is_created_not_when_worker_runs() -> None:
    coordinator, _clipboard, selection, speech, _tracker = make_coordinator()
    selection.text = "captured now"
    job = coordinator.create_job(clipboard_only=False)
    selection.text = "changed later"

    job.run()

    assert speech.requests[0].text == "captured now"


def test_speech_speed_is_captured_when_worker_starts() -> None:
    active_rate = ["+0%"]
    coordinator, _clipboard, _selection, speech, _tracker = make_coordinator(
        speech_rate=lambda: active_rate[0],
    )
    job = coordinator.create_text_job(operation_id="speech-1", workflow_id="workflow", text="hello")
    active_rate[0] = "+25%"

    job.run()
    active_rate[0] = "+50%"

    assert speech.requests[0].rate_override == "+25%"


def test_speech_error_marks_operation_failed() -> None:
    coordinator, _clipboard, _selection, _speech, tracker = make_coordinator(speech=Speech(RuntimeError("tts failed")))
    job = coordinator.create_job(clipboard_only=False)
    with pytest.raises(RuntimeError, match="tts failed"):
        job.run()
    assert tracker.calls == []


def test_cancel_by_old_operation_id_does_not_stop_new_speech() -> None:
    coordinator, _clipboard, _selection, speech, _tracker = make_coordinator()
    old = coordinator.create_text_job(operation_id="old", workflow_id="a", text="old")
    new = coordinator.create_text_job(operation_id="new", workflow_id="b", text="new")
    assert coordinator.cancel_operation(old.operation_id) is False
    assert coordinator.operation_for("b") == new.operation_id
    assert speech.stops == 1
