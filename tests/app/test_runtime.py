from __future__ import annotations

from ClipAI.app.runtime import AppRuntime
from ClipAI.core.commands import ArchiveResult, CloseSession, CopyResult, PasteResult, StartAction, TogglePin, ToggleSpeech
from ClipAI.core.models import ActionDefinition
from ClipAI.core.state import SessionSnapshot, SessionStatus
from ClipAI.services.action_catalog import ActionCatalog


class FakeView:
    def __init__(self) -> None:
        self.snapshots: list[SessionSnapshot] = []
        self.sink = None
        self.stopped = False

    def set_command_sink(self, sink) -> None:
        self.sink = sink

    def render(self, snapshot: SessionSnapshot) -> None:
        self.snapshots.append(snapshot)

    def run(self, command_pump) -> None:
        command_pump()

    def stop(self) -> None:
        self.stopped = True


class FakeSupervisor:
    def __init__(self) -> None:
        self.work: dict[str, object] = {}
        self.cancelled: list[str] = []
        self.closed = False

    def submit(self, session_id, work, on_unhandled_error):
        self.work[session_id] = work

    def cancel(self, session_id) -> None:
        self.cancelled.append(session_id)

    def shutdown(self) -> None:
        self.closed = True


class FakeExecute:
    def execute(self, action, controller) -> None:
        pass

    def execute_follow_up(self, action, text, controller) -> None:
        pass


class FakeOutputs:
    def __init__(self) -> None:
        self.copied: list[str] = []
        self.spoken: list[str] = []
        self.stops = 0
        self.can_speak = True
        self.can_paste = True
        self.can_archive = True
        self.pasted: list[str] = []
        self.archived: list[str] = []

    def copy(self, text: str) -> None:
        self.copied.append(text)

    def speak(self, text: str) -> None:
        self.spoken.append(text)

    def stop_speech(self) -> None:
        self.stops += 1

    def paste(self, text: str) -> None:
        self.pasted.append(text)

    def archive(self, text: str) -> None:
        self.archived.append(text)


class Listener:
    def __init__(self) -> None:
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


class Tray:
    def __init__(self, on_exit) -> None:
        self.on_exit = on_exit
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True


class StatusIndicator:
    def __init__(self) -> None:
        self.statuses: list[str] = []

    def set_status(self, status: str) -> None:
        self.statuses.append(status)

    def set_memory_active(self, active: bool) -> None:
        pass


def make_runtime(*, with_tray: bool = False, status_indicator=None):
    action = ActionDefinition("a", "Action", "ctrl+alt+8", "system", "{input}", {})
    view = FakeView()
    supervisor = FakeSupervisor()
    outputs = FakeOutputs()
    listener = Listener()
    runtime = AppRuntime(
        actions=ActionCatalog([action]),
        execute_action=FakeExecute(),
        output_actions=outputs,
        view=view,
        supervisor=supervisor,
        model="model",
        hotkey_registrar=lambda _map, _callback: listener,
        tray_factory=Tray if with_tray else None,
        status_indicator=status_indicator,
    )
    return runtime, view, supervisor, outputs, listener


def test_latest_start_cancels_previous_unpinned_session() -> None:
    runtime, view, supervisor, _outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    first_id = view.snapshots[-1].session_id
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    assert first_id in supervisor.cancelled
    assert any(s.session_id == first_id and s.status == SessionStatus.CANCELLED for s in view.snapshots)


def test_completed_pinned_session_survives_new_start() -> None:
    runtime, view, supervisor, _outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    session_id = view.snapshots[-1].session_id
    controller = runtime._sessions[session_id]
    controller.transition(SessionStatus.READING_INPUT)
    controller.transition(SessionStatus.PREPARING_REQUEST)
    controller.transition(SessionStatus.REQUESTING_PROVIDER)
    controller.transition(SessionStatus.PROCESSING_RESULT)
    controller.transition(SessionStatus.COMPLETED, content="saved")
    runtime.enqueue(TogglePin(session_id))
    runtime.drain_commands()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    assert session_id not in supervisor.cancelled
    assert controller.snapshot.pinned is True


def test_copy_and_close_are_commands() -> None:
    runtime, view, supervisor, outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    session_id = view.snapshots[-1].session_id
    controller = runtime._sessions[session_id]
    controller._snapshot = controller.snapshot.evolve(content="clean result")
    runtime.enqueue(CopyResult(session_id))
    runtime.enqueue(CloseSession(session_id))
    runtime.drain_commands()
    assert outputs.copied == ["clean result"]
    assert session_id in supervisor.cancelled
    assert session_id not in runtime._sessions


def test_copy_prefers_selected_command_text() -> None:
    runtime, view, _supervisor, outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    session_id = view.snapshots[-1].session_id
    runtime._sessions[session_id]._snapshot = runtime._sessions[session_id].snapshot.evolve(content="full result")
    runtime.enqueue(CopyResult(session_id, " selected "))
    runtime.drain_commands()
    assert outputs.copied == ["selected"]


def test_stop_releases_listener_supervisor_and_view() -> None:
    runtime, view, supervisor, _outputs, listener = make_runtime()
    runtime.start()
    runtime.stop()
    assert listener.stopped and supervisor.closed and view.stopped


def test_tray_exit_uses_typed_shutdown_command() -> None:
    runtime, view, supervisor, _outputs, listener = make_runtime(with_tray=True)
    runtime.start()
    tray = runtime._tray
    assert tray is not None and tray.started
    tray.on_exit()
    runtime.drain_commands()
    assert tray.stopped and listener.stopped and supervisor.closed and view.stopped


def test_speech_runs_as_supervised_output_and_can_stop() -> None:
    runtime, view, supervisor, outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    session_id = view.snapshots[-1].session_id
    controller = runtime._sessions[session_id]
    controller._snapshot = controller.snapshot.evolve(content="speak me")
    runtime.enqueue(ToggleSpeech(session_id))
    runtime.drain_commands()
    assert controller.snapshot.speaking is True
    work = supervisor.work[f"speech:{session_id}"]
    work()
    assert outputs.spoken == ["speak me"]
    assert controller.snapshot.speaking is False


def test_speech_prefers_selected_command_text() -> None:
    runtime, view, supervisor, outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    session_id = view.snapshots[-1].session_id
    runtime._sessions[session_id]._snapshot = runtime._sessions[session_id].snapshot.evolve(content="full")
    runtime.enqueue(ToggleSpeech(session_id, "selected"))
    runtime.drain_commands()
    supervisor.work[f"speech:{session_id}"]()
    assert outputs.spoken == ["selected"]


def test_speech_reports_one_external_api_lifecycle() -> None:
    indicator = StatusIndicator()
    runtime, view, supervisor, _outputs, _listener = make_runtime(status_indicator=indicator)
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    session_id = view.snapshots[-1].session_id
    runtime._sessions[session_id]._snapshot = runtime._sessions[session_id].snapshot.evolve(content="speak")
    runtime.enqueue(ToggleSpeech(session_id))
    runtime.drain_commands()
    supervisor.work[f"speech:{session_id}"]()
    assert indicator.statuses == ["processing", "success"]


def test_paste_and_archive_flow_through_typed_commands() -> None:
    runtime, view, _supervisor, outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    session_id = view.snapshots[-1].session_id
    controller = runtime._sessions[session_id]
    controller._snapshot = controller.snapshot.evolve(content="use me")
    runtime.enqueue(ArchiveResult(session_id))
    runtime.drain_commands()
    assert outputs.archived == ["use me"]
    runtime.enqueue(PasteResult(session_id, "selected"))
    runtime.drain_commands()
    assert session_id not in runtime._sessions
    _supervisor.work[f"paste:{session_id}"]()
    assert outputs.pasted == ["selected"]
