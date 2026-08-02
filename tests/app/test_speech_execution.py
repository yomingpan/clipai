from __future__ import annotations

import asyncio
import threading

from ClipAI.app.speech_execution import SupervisedSpeechResultSink
from ClipAI.app.task_supervisor import TaskSupervisor
from ClipAI.core.state import CancellationToken
from ClipAI.services.speech_coordinator import SpeechCoordinator, SpeechVoiceSelector


class _Reader:
    def read_text(self) -> str:
        return ""


class _Speech:
    def __init__(self) -> None:
        self.texts: list[str] = []

    def speak(self, request) -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise AssertionError("blocking speech ran on the provider asyncio loop")
        self.texts.append(request.text)

    def stop(self) -> None:
        pass


class _RecordingSupervisor:
    def __init__(self) -> None:
        self.task_classes: list[str] = []

    async def run(self, _task_id, work, *, task_class, cancellation_hook) -> None:
        del cancellation_hook
        self.task_classes.append(task_class)
        await asyncio.to_thread(work)


class _BlockingSpeech:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.stopped = threading.Event()

    def speak(self, request) -> None:
        self.started.set()
        while not request.cancellation.is_cancelled and not self.stopped.wait(0.01):
            pass

    def stop(self) -> None:
        self.stopped.set()


def test_generated_speech_runs_in_the_media_lane_outside_provider_loop() -> None:
    speech = _Speech()
    coordinator = SpeechCoordinator(
        clipboard=_Reader(),
        selection_reader=_Reader(),
        speech=speech,
        voice_selector=SpeechVoiceSelector("en-GB-TestVoice"),
    )
    supervisor = TaskSupervisor()
    sink = SupervisedSpeechResultSink(coordinator, supervisor)

    try:
        asyncio.run(sink.speak_result("generated answer", "workflow-1", CancellationToken()))
    finally:
        supervisor.shutdown()

    assert speech.texts == ["generated answer"]


def test_generated_speech_uses_the_isolated_media_lane() -> None:
    speech = _Speech()
    coordinator = SpeechCoordinator(
        clipboard=_Reader(),
        selection_reader=_Reader(),
        speech=speech,
        voice_selector=SpeechVoiceSelector("en-GB-TestVoice"),
    )
    supervisor = _RecordingSupervisor()

    asyncio.run(
        SupervisedSpeechResultSink(coordinator, supervisor).speak_result(
            "generated answer",
            "workflow-1",
            CancellationToken(),
        )
    )

    assert supervisor.task_classes == ["media"]


def test_cancelling_provider_work_stops_generated_speech() -> None:
    speech = _BlockingSpeech()
    coordinator = SpeechCoordinator(
        clipboard=_Reader(),
        selection_reader=_Reader(),
        speech=speech,
        voice_selector=SpeechVoiceSelector("en-GB-TestVoice"),
    )
    supervisor = TaskSupervisor()
    sink = SupervisedSpeechResultSink(coordinator, supervisor)

    async def exercise() -> None:
        task = asyncio.create_task(
            sink.speak_result("generated answer", "workflow-1", CancellationToken())
        )
        assert await asyncio.to_thread(speech.started.wait, 1)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError("speech task was not cancelled")
        assert speech.stopped.wait(1)

    try:
        asyncio.run(exercise())
    finally:
        supervisor.shutdown()
