from __future__ import annotations

from ClipAI.app.runtime import AppRuntime
from ClipAI.core.commands import ArchiveResult, CloseSession, CopyResult, ExportDiagnostics, PasteResult, SpeakSelectionOrClipboard, StartAction, TogglePin, ToggleSpeech
from ClipAI.core.models import ActiveWorkflowContext, ActionDefinition, ShortcutDefinition, WorkflowStep
from ClipAI.core.state import SessionSnapshot, SessionStatus
from ClipAI.services.action_catalog import ActionCatalog
from ClipAI.services.shortcut_catalog import ShortcutCatalog


class FakeView:
    def __init__(self) -> None:
        self.snapshots: list[SessionSnapshot] = []
        self.sink = None
        self.stopped = False
        self.context: ActiveWorkflowContext | None = None

    def set_command_sink(self, sink) -> None:
        self.sink = sink

    def render(self, snapshot: SessionSnapshot) -> None:
        self.snapshots.append(snapshot)

    def run(self, command_pump) -> None:
        command_pump()

    def stop(self) -> None:
        self.stopped = True

    def active_workflow_context(self) -> ActiveWorkflowContext | None:
        return self.context


class FakeSupervisor:
    def __init__(self) -> None:
        self.work: dict[str, object] = {}
        self.cancelled: list[str] = []
        self.closed = False
        self.error_handlers: dict[str, object] = {}

    def submit(self, session_id, work, on_unhandled_error):
        self.work[session_id] = work
        self.error_handlers[session_id] = on_unhandled_error

    def cancel(self, session_id) -> None:
        self.cancelled.append(session_id)

    def shutdown(self) -> None:
        self.closed = True


class FakeExecute:
    def __init__(self) -> None:
        self.invocations = []

    def execute(self, action, controller) -> None:
        pass

    def execute_follow_up(self, action, text, controller) -> None:
        pass

    def execute_invocation(self, action, invocation, controller) -> None:
        self.invocations.append(invocation)

    def execute_follow_up_invocation(self, *args, **kwargs) -> None:
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


class Operation:
    def __init__(self, events: list[tuple[str, ...]], operation_id: str) -> None:
        self.events = events
        self.operation_id = operation_id

    def succeed(self) -> None:
        self.events.append(("success", self.operation_id))

    def fail(self) -> None:
        self.events.append(("error", self.operation_id))

    def cancel(self) -> None:
        self.events.append(("cancel", self.operation_id))


class OperationTracker:
    def __init__(self) -> None:
        self.events: list[tuple[str, ...]] = []
        self.stopped = False

    def start(self, operation_id: str, kind: str):
        self.events.append(("start", operation_id, kind))
        return Operation(self.events, operation_id)

    def stop(self) -> None:
        self.stopped = True


class Exporter:
    def __init__(self, destination="diagnostics.zip", error=None) -> None:
        self.destination = destination
        self.error = error

    def export(self):
        if self.error:
            raise self.error
        return self.destination


class Notifier:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def notify(self, title: str, message: str) -> None:
        self.messages.append((title, message))


class SpeechJob:
    operation_id = "tts:clipboard:unique"

    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def run(self) -> None:
        self.calls.append("run")


class GlobalSpeech:
    def __init__(self) -> None:
        self.clipboard_only: list[bool] = []
        self.calls: list[str] = []
        self.cancelled = 0

    def create_job(self, *, clipboard_only: bool) -> SpeechJob:
        self.clipboard_only.append(clipboard_only)
        return SpeechJob(self.calls)

    def cancel_current(self) -> None:
        self.cancelled += 1


def make_runtime(*, with_tray: bool = False, operation_tracker=None, diagnostics_exporter=None, notifier=None, speech_coordinator=None):
    action = ActionDefinition("a", "Action", "system", "{input}", {})
    shorten = ActionDefinition("shorten", "Shorten", "system", "{input}", {}, input_policy="contextual_text")
    view = FakeView()
    supervisor = FakeSupervisor()
    outputs = FakeOutputs()
    listener = Listener()
    runtime = AppRuntime(
        actions=ActionCatalog([action, shorten]),
        shortcuts=ShortcutCatalog([
            ShortcutDefinition("a", "ctrl+alt+8", "start_action", "a"),
            ShortcutDefinition("speech", "ctrl+alt+q", "speak_selection_or_clipboard"),
            ShortcutDefinition("shorten", "ctrl+alt+x", "start_action", "shorten"),
        ]),
        execute_action=FakeExecute(),
        output_actions=outputs,
        view=view,
        supervisor=supervisor,
        model="model",
        hotkey_registrar=lambda _map, _callback: listener,
        tray_factory=Tray if with_tray else None,
        operation_tracker=operation_tracker,
        diagnostics_exporter=diagnostics_exporter,
        notifier=notifier,
        speech_coordinator=speech_coordinator,
    )
    return runtime, view, supervisor, outputs, listener


def test_global_speech_command_is_supervised_without_creating_session() -> None:
    speech = GlobalSpeech()
    runtime, view, supervisor, _outputs, _listener = make_runtime(speech_coordinator=speech)
    runtime.enqueue(SpeakSelectionOrClipboard())
    runtime.drain_commands()
    assert speech.clipboard_only == [False]
    assert view.snapshots == []
    work = supervisor.work["speech:tts:clipboard:unique"]
    work()
    assert speech.calls == ["run"]


def test_global_speech_uses_clipboard_only_when_session_exists() -> None:
    speech = GlobalSpeech()
    runtime, _view, _supervisor, _outputs, _listener = make_runtime(speech_coordinator=speech)
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    runtime.enqueue(SpeakSelectionOrClipboard())
    runtime.drain_commands()
    assert speech.clipboard_only == [True]


def test_contextual_action_reuses_active_workflow_and_prefers_popup_selection() -> None:
    runtime, view, supervisor, _outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    workflow_id = view.snapshots[-1].session_id
    controller = runtime._workflows[workflow_id]
    old_invocation = controller.snapshot.active_invocation_id
    step = WorkflowStep("step-1", "a", "Action", "input", "full popup result", "plain_text")
    controller._snapshot = controller.snapshot.evolve(
        status=SessionStatus.COMPLETED,
        content=step.result_text,
        steps=(step,),
        displayed_step_index=0,
        active_invocation_id=None,
    )
    view.context = ActiveWorkflowContext(workflow_id, step.step_id, step.result_text, "selected popup text")

    runtime.enqueue(StartAction("shorten", "long"))
    runtime.drain_commands()

    assert len(runtime._workflows) == 1
    assert runtime._foreground_id == workflow_id
    new_invocation = controller.snapshot.active_invocation_id
    assert new_invocation != old_invocation
    supervisor.work[new_invocation]()
    invocation = runtime._execute_action.invocations[-1]
    assert invocation.input_target.document.text == "selected popup text"
    assert invocation.parent_step_id == "step-1"


def test_contextual_action_without_popup_context_creates_external_workflow() -> None:
    runtime, _view, _supervisor, _outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("shorten", "short"))
    runtime.drain_commands()
    controller = next(iter(runtime._workflows.values()))
    assert controller.snapshot.active_invocation_id is not None


def test_latest_start_cancels_previous_unpinned_session() -> None:
    runtime, view, supervisor, _outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    first_id = view.snapshots[-1].session_id
    first_invocation = runtime._workflows[first_id].snapshot.active_invocation_id
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    assert first_invocation in supervisor.cancelled
    assert any(s.session_id == first_id and s.status == SessionStatus.CANCELLED for s in view.snapshots)


def test_completed_pinned_session_survives_new_start() -> None:
    runtime, view, supervisor, _outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    session_id = view.snapshots[-1].session_id
    controller = runtime._workflows[session_id]
    controller._snapshot = controller.snapshot.evolve(status=SessionStatus.COMPLETED, content="saved")
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
    controller = runtime._workflows[session_id]
    active_invocation = controller.snapshot.active_invocation_id
    controller._snapshot = controller.snapshot.evolve(content="clean result")
    runtime.enqueue(CopyResult(session_id))
    runtime.enqueue(CloseSession(session_id))
    runtime.drain_commands()
    assert outputs.copied == ["clean result"]
    assert active_invocation in supervisor.cancelled
    assert session_id not in runtime._workflows


def test_copy_prefers_selected_command_text() -> None:
    runtime, view, _supervisor, outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    session_id = view.snapshots[-1].session_id
    runtime._workflows[session_id]._snapshot = runtime._workflows[session_id].snapshot.evolve(content="full result")
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
    controller = runtime._workflows[session_id]
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
    runtime._workflows[session_id]._snapshot = runtime._workflows[session_id].snapshot.evolve(content="full")
    runtime.enqueue(ToggleSpeech(session_id, "selected"))
    runtime.drain_commands()
    supervisor.work[f"speech:{session_id}"]()
    assert outputs.spoken == ["selected"]


def test_speech_reports_one_external_api_lifecycle() -> None:
    operations = OperationTracker()
    runtime, view, supervisor, _outputs, _listener = make_runtime(operation_tracker=operations)
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    session_id = view.snapshots[-1].session_id
    runtime._workflows[session_id]._snapshot = runtime._workflows[session_id].snapshot.evolve(content="speak")
    runtime.enqueue(ToggleSpeech(session_id))
    runtime.drain_commands()
    supervisor.work[f"speech:{session_id}"]()
    assert operations.events == [("start", f"tts:{session_id}", "tts"), ("success", f"tts:{session_id}")]


def test_diagnostics_export_is_typed_supervised_work_with_feedback() -> None:
    notifier = Notifier()
    runtime, _view, supervisor, _outputs, _listener = make_runtime(
        diagnostics_exporter=Exporter("C:/diagnostics/report.zip"),
        notifier=notifier,
    )
    runtime.enqueue(ExportDiagnostics())
    runtime.drain_commands()
    supervisor.work["diagnostics:export"]()
    assert notifier.messages == [("ClipAI Diagnostics", "Exported to C:/diagnostics/report.zip")]


def test_diagnostics_export_failure_reports_incident() -> None:
    notifier = Notifier()
    runtime, _view, supervisor, _outputs, _listener = make_runtime(
        diagnostics_exporter=Exporter(error=OSError("disk full")),
        notifier=notifier,
    )
    runtime.enqueue(ExportDiagnostics())
    runtime.drain_commands()
    try:
        supervisor.work["diagnostics:export"]()
    except OSError as error:
        supervisor.error_handlers["diagnostics:export"](error)
    assert "Export failed. Incident:" in notifier.messages[-1][1]


def test_paste_and_archive_flow_through_typed_commands() -> None:
    runtime, view, _supervisor, outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    session_id = view.snapshots[-1].session_id
    controller = runtime._workflows[session_id]
    controller._snapshot = controller.snapshot.evolve(content="use me")
    runtime.enqueue(ArchiveResult(session_id))
    runtime.drain_commands()
    assert outputs.archived == ["use me"]
    runtime.enqueue(PasteResult(session_id, "selected"))
    runtime.drain_commands()
    assert session_id not in runtime._workflows
    _supervisor.work[f"paste:{session_id}"]()
    assert outputs.pasted == ["selected"]
