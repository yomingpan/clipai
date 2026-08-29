from __future__ import annotations

import asyncio
from dataclasses import replace
import pytest

from ClipAI.app.runtime import AppRuntime
from ClipAI.app.runtime_outputs import ResultOutputRuntimeModule
from ClipAI.app.runtime_provider_configuration import ProviderConfigurationRuntimeModule
from ClipAI.app.runtime_action_feedback import ActionFeedbackRuntimeModule
from ClipAI.app.runtime_user_preferences import UserPreferencesRuntimeModule
from ClipAI.app.runtime_workflows import VoiceCaptureIntent, WorkflowRuntimeModule
from ClipAI.core.commands import ActivateWorkflow, ArchiveResult, CancelSession, CloseSession, CopyResult, ExportDiagnostics, ExternalForegroundChanged, FollowUp, InterruptionRequested, InterruptAll, InterruptCurrent, OpenContextualQuestion, OpenProviderSettings, PasteOperationCompleted, PasteResult, RefreshProviderModels, ReloadConfiguration, ResetFirstUseHints, SelectProvider, SelectProviderModel, SetFirstUseHintsEnabled, SetSpeechSpeed, ShortcutPressInvoked, SpeakSelectionOrClipboard, StartAction, SubmitActionFeedback, SubmitContextualQuestion, TogglePin, ToggleSpeech, ValidateAndSaveProviderSettings, WorkflowAttentionCompleted
from ClipAI.core.errors import InputError, PersonalStyleUnavailableError
from ClipAI.core.models import ActiveWorkflowContext, ActionDefinition, ActionFeedbackContract, ActionInvocation, ControlSurfaceRef, EntryActionRef, EnvironmentSetting, FeedbackReason, GuidancePreferences, InputDocument, InputTarget, ModelSelectionState, OutputOperationIntent, PasteOutcome, PasteRequest, PasteTarget, PersonalStyleProfile, ProviderCapabilities, ProviderOption, ProviderSelectionState, ProviderSettingsInput, ProviderSettingsState, ReadinessIssue, ShortcutDefinition, ShortcutObservationSnapshot, ShortcutPressId, UserPreferences, WorkflowStep
from ClipAI.core.state import SessionSnapshot, SessionStatus
from ClipAI.core.voice import VoiceCaptureSurfaceContext, VoiceFollowUpTarget, VoiceOrigin
from ClipAI.services.action_catalog import ActionCatalog
from ClipAI.services.shortcut_catalog import ShortcutCatalog
from ClipAI.providers.fake import FakeProvider
from ClipAI.services.provider_binding import ProviderExecutionBinding, ProviderRuntimeSnapshot
from ClipAI.services.provider_configuration import ProviderConfigurationCoordinator
from ClipAI.services.user_preferences import UserPreferencesCoordinator
from ClipAI.services.paste_target import PasteTargetCoordinator
from ClipAI.services.recent_actions import RecentActionHistory
from ClipAI.support.diagnostics import IncidentReporter


class FakeView:
    def __init__(self) -> None:
        self.snapshots: list[SessionSnapshot] = []
        self.sink = None
        self.stopped = False
        self.context: ActiveWorkflowContext | None = None
        self.output_results = []
        self.provider_settings_states = []
        self.workflow_controller = lambda _workflow_id: None
        self.execute_action = None
        self.actions = None
        self.speech_coordinator = None
        self.paste_target_states = []
        self.attentions = []

    def set_command_sink(self, sink) -> None:
        self.sink = sink

    def render(self, snapshot: SessionSnapshot) -> None:
        self.snapshots.append(snapshot)

    def run(self, command_pump) -> None:
        command_pump()

    def stop(self) -> None:
        self.stopped = True

    def workflow_context(self, workflow_id: str) -> ActiveWorkflowContext | None:
        return self.context if self.context is not None and self.context.workflow_id == workflow_id else None

    def present_output_operation(self, result) -> None:
        self.output_results.append(result)

    def present_paste_target(self, target) -> None:
        self.paste_target_states.append(target)

    def present_workflow_attention(self, attention) -> None:
        self.attentions.append(attention)

    def show_provider_settings(self, state) -> None:
        self.provider_settings_states.append(state)

    def set_provider_settings(self, state) -> None:
        self.provider_settings_states.append(state)


class FakeSupervisor:
    def __init__(self, submit_error: BaseException | None = None) -> None:
        self.work: dict[str, object] = {}
        self.cancelled: list[str] = []
        self.closed = False
        self.error_handlers: dict[str, object] = {}
        self.cancellation_hooks: dict[str, object] = {}
        self.submit_error = submit_error

    def submit(self, session_id, work, on_unhandled_error, **kwargs):
        if self.submit_error is not None:
            raise self.submit_error
        self.work[session_id] = work
        self.error_handlers[session_id] = on_unhandled_error
        if kwargs.get("cancellation_hook") is not None:
            self.cancellation_hooks[session_id] = kwargs["cancellation_hook"]

    def cancel(self, session_id) -> None:
        self.cancelled.append(session_id)
        hook = self.cancellation_hooks.get(session_id)
        if hook is not None:
            hook()

    def cancel_many(self, session_ids, on_settled) -> None:
        for session_id in dict.fromkeys(session_ids):
            self.cancel(session_id)
        on_settled()

    def shutdown(self) -> None:
        self.closed = True


class FakeProviderExecution:
    def __init__(self, supervisor: FakeSupervisor) -> None:
        self.supervisor = supervisor
        self.closed = False

    def start(self, operation_id, work, on_result, on_error, on_cancelled) -> None:
        if self.supervisor.submit_error is not None:
            raise self.supervisor.submit_error

        def run() -> None:
            try:
                result = asyncio.run(work())
            except asyncio.CancelledError:
                on_cancelled()
            except BaseException as error:
                on_error(error)
            else:
                on_result(result)

        self.supervisor.work[operation_id] = run
        self.supervisor.error_handlers[operation_id] = on_error

    def cancel(self, operation_id) -> bool:
        self.supervisor.cancel(operation_id)
        return operation_id in self.supervisor.work

    def shutdown(self) -> None:
        self.closed = True


class FakeExecute:
    def __init__(self) -> None:
        self.invocations = []
        self.models = []
        self.bindings = []
        self.follow_ups = []
        self.actions = []

    def execute(self, action, controller) -> None:
        pass

    def execute_follow_up(self, action, text, controller) -> None:
        pass

    async def execute_invocation(self, action, invocation, controller, *, binding) -> None:
        self.actions.append(action)
        self.invocations.append(invocation)
        self.models.append(binding.model)
        self.bindings.append(binding)

    async def execute_follow_up_invocation(self, *args, **kwargs) -> None:
        self.follow_ups.append((args, kwargs))


class ContextResolver:
    def __init__(self) -> None:
        self.document = InputDocument("fixed selected source", "selection")

    def resolve_text(self, _cancellation=None):
        return self.document


class FakeOutputs:
    def __init__(self) -> None:
        self.copied: list[str] = []
        self.spoken: list[str] = []
        self.stops = 0
        self.can_speak = True
        self.can_archive = True
        self.pasted: list[str] = []
        self.archived: list[str] = []
        self.paste_targets: list[PasteTarget] = []
        self.clipboard_bits = b"\x00\xfforiginal\x00"
        self.copy_error: Exception | None = None

    def copy(self, text: str) -> None:
        if self.copy_error is not None:
            raise self.copy_error
        self.copied.append(text)
        self.clipboard_bits = text.encode("utf-8")

    def speak(self, text: str) -> None:
        self.spoken.append(text)

    def archive(self, text: str) -> None:
        self.archived.append(text)


class FakePasteOperations:
    def __init__(self, outputs: FakeOutputs, completion_sink) -> None:
        self.outputs = outputs
        self.completion_sink = completion_sink
        self.active: PasteRequest | None = None
        self.cancel_requested = False
        self.running = False

    def admit(self, request: PasteRequest) -> bool:
        if self.active is not None:
            self.completion_sink(PasteOperationCompleted(
                request.operation_id,
                request.workflow_id,
                PasteOutcome("failed", "not_dispatched", "not_required", "Paste still in progress."),
            ))
            return False
        self.active = request
        self.cancel_requested = False
        self.running = False
        return True

    def execute(self, operation_id: str) -> None:
        request = self.active
        if request is None or request.operation_id != operation_id:
            return
        self.running = True
        if self.cancel_requested:
            outcome = PasteOutcome("cancelled", "not_dispatched", "not_required")
        else:
            self.outputs.pasted.append(request.text)
            self.outputs.paste_targets.append(request.target)
            outcome = PasteOutcome(
                "dispatched_unconfirmed",
                "dispatched_unconfirmed",
                "restored",
                "Paste command was sent; confirm the target before trying again.",
            )
        self._complete(request, outcome)

    def request_cancel(self, operation_id: str) -> bool:
        request = self.active
        if request is None or request.operation_id != operation_id:
            return False
        self.cancel_requested = True
        if not self.running:
            self._complete(request, PasteOutcome("cancelled", "not_dispatched", "not_required"))
        return True

    def request_cancel_for_workflow(self, workflow_id: str) -> str | None:
        request = self.active
        if request is None or request.workflow_id != workflow_id:
            return None
        self.request_cancel(request.operation_id)
        return request.operation_id

    def request_cancel_active(self) -> str | None:
        request = self.active
        if request is None:
            return None
        self.request_cancel(request.operation_id)
        return request.operation_id

    def fail_to_start(self, operation_id: str, error: BaseException) -> bool:
        request = self.active
        if request is None or request.operation_id != operation_id:
            return False
        self._complete(
            request,
            PasteOutcome("failed", "not_dispatched", "not_required", str(error)),
        )
        return True

    def mark_running(self, operation_id: str) -> None:
        assert self.active is not None and self.active.operation_id == operation_id
        self.running = True

    def finish_running_cancel(self) -> None:
        assert self.active is not None and self.cancel_requested
        self._complete(
            self.active,
            PasteOutcome("cancelled", "not_dispatched", "not_required"),
        )

    def _complete(self, request: PasteRequest, outcome: PasteOutcome) -> None:
        if self.active is not request:
            return
        self.completion_sink(PasteOperationCompleted(request.operation_id, request.workflow_id, outcome))
        self.active = None
        self.running = False


class Listener:
    def __init__(self) -> None:
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True

    def observe(self):
        class Lease:
            snapshot = ShortcutObservationSnapshot()

            def close(self) -> None:
                pass

        return Lease()


class Monitor:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True


class Tray:
    def __init__(self, on_exit) -> None:
        self.on_exit = on_exit
        self.started = False
        self.stopped = False
        self.model_selections = []
        self.provider_selections = []
        self.guidance_preferences = []
        self.speech_speeds = []

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def set_model_selection(self, selection) -> None:
        self.model_selections.append(selection)

    def set_provider_selection(self, selection) -> None:
        self.provider_selections.append(selection)

    def set_guidance_preferences(self, preferences) -> None:
        self.guidance_preferences.append(preferences)

    def set_speech_speed(self, state) -> None:
        self.speech_speeds.append(state)


class ModelPreferences:
    def __init__(self, error=None) -> None:
        self.saved = []
        self.error = error

    def save_settings(self, settings) -> None:
        if self.error:
            raise self.error
        self.saved.extend((setting.name, setting.value) for setting in settings)


class RuntimeProviderBackend:
    def __init__(self, snapshot, preferences=None, reload=None, validate=None, build=None, discover=None) -> None:
        self.snapshot = snapshot
        self.preferences = preferences or ModelPreferences()
        self.reload_callback = reload
        self.validate = validate
        self.build = build
        self.discover = discover

    def reload(self):
        return self.reload_callback() if self.reload_callback is not None else self.snapshot

    def persist_provider(self, provider):
        current = self.reload()
        self.preferences.save_settings((EnvironmentSetting("CLIPAI_PROVIDER", provider),))
        self.snapshot = ProviderRuntimeSnapshot(provider, current.bindings, current.options, current.connection_name, current.connection_base_url)
        return self.snapshot

    def persist_model(self, provider, model):
        current = self.reload()
        env_name = "CLIPAI_GATEWAY_MODEL" if provider == "gateway" else f"{provider.upper()}_MODEL"
        self.preferences.save_settings((EnvironmentSetting(env_name, model),))
        bindings = tuple(
            ProviderExecutionBinding(item.provider, item.provider_id, model, item.readiness_issues) if item.provider_id == provider else item
            for item in current.bindings
        )
        options = tuple(
            ProviderOption(item.provider_id, item.display_name, item.available_models, model, item.configured, item.custom_models, item.credential_hint, item.capabilities)
            if item.provider_id == provider else item
            for item in current.options
        )
        self.snapshot = ProviderRuntimeSnapshot(current.active_provider, bindings, options, current.connection_name, current.connection_base_url)
        return self.snapshot

    async def validate_save_and_build(self, settings):
        if self.validate is not None:
            self.validate(settings.provider, settings.api_key, settings.connection_base_url, settings.model)
        candidate = self.build(settings.provider, settings.model, settings.api_key, settings.connection_name, settings.connection_base_url) if self.build is not None else self.snapshot
        updates = [EnvironmentSetting("CLIPAI_PROVIDER", settings.provider)]
        if settings.provider == "gateway":
            updates.extend((EnvironmentSetting("CLIPAI_GATEWAY_NAME", settings.connection_name), EnvironmentSetting("CLIPAI_GATEWAY_BASE_URL", settings.connection_base_url)))
            if settings.api_key:
                updates.append(EnvironmentSetting("CLIPAI_GATEWAY_API_KEY", settings.api_key))
            updates.append(EnvironmentSetting("CLIPAI_GATEWAY_MODEL", settings.model))
        else:
            if settings.api_key:
                updates.append(EnvironmentSetting(f"{settings.provider.upper()}_API_KEY", settings.api_key))
            updates.append(EnvironmentSetting(f"{settings.provider.upper()}_MODEL", settings.model))
        self.preferences.save_settings(tuple(updates))
        self.snapshot = candidate
        return candidate

    async def discover_models(self, provider, connection):
        return self.discover(provider, connection) if self.discover is not None else ()


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

    def report_error(self, message, suggestion="") -> None:
        self.events.append(("report_error", message, suggestion))

    def report_waiting(self) -> None:
        self.events.append(("waiting",))

    @property
    def last_error(self):
        return None


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


class MissingPersonalStyles:
    def bind(self, action):
        if action.personal_style_mode is None:
            return action
        raise PersonalStyleUnavailableError("尚未選擇個人風格。")


class SwitchingPersonalStyles:
    def __init__(self) -> None:
        self.active = PersonalStyleProfile("first", "First", "first voice", "hash-first")

    def bind(self, action):
        return self.bind_to(action, self.active)

    @staticmethod
    def bind_to(action, profile):
        return replace(action, personal_style=profile, version_id=f"{action.version_id}:{profile.profile_id}")


class SpeechJob:
    operation_id = "tts:clipboard:unique"
    workflow_id = "global"

    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def run(self) -> None:
        self.calls.append("run")


class GlobalSpeech:
    def __init__(self) -> None:
        self.clipboard_only: list[bool] = []
        self.calls: list[str] = []
        self.cancelled = 0
        self.current = None

    def create_job(self, *, clipboard_only: bool) -> SpeechJob:
        self.clipboard_only.append(clipboard_only)
        self.current = (SpeechJob.operation_id, SpeechJob.workflow_id)
        return SpeechJob(self.calls)

    def cancel_current(self) -> None:
        if self.current is not None:
            self.cancel_operation(self.current[0])

    def cancel_operation(self, operation_id: str) -> bool:
        if self.current is None or self.current[0] != operation_id:
            return False
        self.current = None
        self.cancelled += 1
        return True

    def operation_for(self, workflow_id: str):
        return self.current[0] if self.current is not None and self.current[1] == workflow_id else None

    def cancel_workflow(self, workflow_id: str) -> bool:
        operation_id = self.operation_for(workflow_id)
        return self.cancel_operation(operation_id) if operation_id is not None else False

    @property
    def current_identity(self):
        return self.current


class PopupSpeech:
    def __init__(self, outputs: FakeOutputs) -> None:
        self.outputs = outputs
        self.current = None

    @property
    def current_identity(self):
        return self.current

    def operation_for(self, workflow_id):
        return self.current[0] if self.current and self.current[1] == workflow_id else None

    def create_text_job(self, *, operation_id, workflow_id, text):
        self.current = (operation_id, workflow_id)
        owner = self
        class Job:
            def run(self):
                owner.outputs.spoken.append(text)
                if owner.current == (operation_id, workflow_id):
                    owner.current = None
        return Job()

    def create_job(self, *, clipboard_only):
        del clipboard_only
        return SpeechJob([])

    def cancel_operation(self, operation_id):
        if self.current is None or self.current[0] != operation_id:
            return False
        self.current = None
        self.outputs.stops += 1
        return True

    def cancel_workflow(self, workflow_id):
        operation_id = self.operation_for(workflow_id)
        return self.cancel_operation(operation_id) if operation_id else False

    def cancel_current(self):
        if self.current:
            self.cancel_operation(self.current[0])


def make_runtime(*, with_tray: bool = False, operation_tracker=None, diagnostics_exporter=None, notifier=None, speech_coordinator=None, model_preferences=None, reload_provider_settings=None, validate_provider_credential=None, build_provider_candidate=None, discover_provider_models=None, action_feedback=None, guidance_preferences=None, guidance_preferences_presenter=None, speech_speed_presenter=None, submit_error=None, include_voice_input: bool = False, personal_styles=None, entry_panel=None, recent_actions=None, recent_action_sink=None):
    action = ActionDefinition(
        "a",
        "Action",
        "system",
        "{input}",
        {},
        personal_style_mode="informal" if personal_styles is not None else None,
    )
    shorten = ActionDefinition(
        "shorten",
        "Shorten",
        "system",
        "{input}",
        {},
        feedback_contract=ActionFeedbackContract(
            "Shorten faithfully",
            "Do not change meaning",
            (FeedbackReason("meaning_lost", "Meaning lost"),),
        ),
    )
    view = FakeView()
    supervisor = FakeSupervisor(submit_error)
    provider_execution = FakeProviderExecution(supervisor)
    outputs = FakeOutputs()
    speech_coordinator = speech_coordinator or PopupSpeech(outputs)
    listener = Listener()
    snapshot = ProviderRuntimeSnapshot(
        "openai",
        (
            ProviderExecutionBinding(FakeProvider(), "openai", "model"),
            ProviderExecutionBinding(FakeProvider(), "gemini", "gemini-model"),
        ),
        (
            ProviderOption("openai", "OpenAI", ("model", "new-model"), "model", True),
            ProviderOption("gemini", "Gemini", ("gemini-model",), "gemini-model", True),
        ),
    )
    backend = RuntimeProviderBackend(
        snapshot,
        model_preferences,
        reload_provider_settings,
        validate_provider_credential,
        build_provider_candidate,
        discover_provider_models,
    )
    shortcut_definitions = [
        ShortcutDefinition("contextual_question", "ctrl+alt+r", "open_contextual_question"),
        ShortcutDefinition("a", "ctrl+alt+8", "start_action", "a"),
        ShortcutDefinition("speech", "ctrl+alt+q", "speak_selection_or_clipboard"),
        ShortcutDefinition("shorten", "ctrl+alt+x", "start_action", "shorten"),
    ]
    if include_voice_input:
        shortcut_definitions.append(ShortcutDefinition("voice_input", "ctrl+alt+w", "push_to_talk"))
    shortcuts = ShortcutCatalog(shortcut_definitions)
    actions = ActionCatalog([action, shorten])
    execute_action = FakeExecute()
    provider_configuration = ProviderConfigurationCoordinator(snapshot, backend)
    incident_reporter = IncidentReporter()
    paste_targets = PasteTargetCoordinator(view)
    paste_targets.observe(PasteTarget("hwnd:10", 42, "Notepad", "Untitled", 1))
    runtime_holder = []
    enqueue = lambda command: runtime_holder[0].enqueue(command)
    workflow_module = WorkflowRuntimeModule(
        actions=actions,
        shortcuts=shortcuts,
        execute_action=execute_action,
        view=view,
        provider_execution=provider_execution,
        enqueue=enqueue,
        provider_configuration=provider_configuration,
        workflow_context_reader=view,
        incident_reporter=incident_reporter,
        operation_tracker=operation_tracker,
        notifier=notifier,
        speech_coordinator=speech_coordinator,
        attention_presenter=view,
        personal_styles=personal_styles,
        input_resolver=ContextResolver(),
        supervisor=supervisor,
        recent_actions=recent_actions,
        recent_action_sink=recent_action_sink,
    )
    output_module = ResultOutputRuntimeModule(
        output_actions=outputs,
        paste_operations=FakePasteOperations(outputs, enqueue),
        supervisor=supervisor,
        workflow_controller=workflow_module.controller_for,
        output_operation_presenter=view,
        incident_reporter=incident_reporter,
        operation_tracker=operation_tracker,
        diagnostics_exporter=diagnostics_exporter,
        notifier=notifier,
        speech_coordinator=speech_coordinator,
        paste_targets=paste_targets,
    )
    provider_module = ProviderConfigurationRuntimeModule(
        coordinator=provider_configuration,
        provider_execution=provider_execution,
        enqueue=enqueue,
        operation_tracker=operation_tracker,
        provider_settings_presenter=view,
    )
    action_feedback_module = ActionFeedbackRuntimeModule(
        supervisor=supervisor,
        workflow_controller=workflow_module.controller_for,
        enqueue=enqueue,
        action_feedback=action_feedback,
    )
    user_preferences_module = UserPreferencesRuntimeModule(
        supervisor=supervisor,
        enqueue=enqueue,
        user_preferences=guidance_preferences,
        guidance_preferences_presenter=guidance_preferences_presenter,
        speech_speed_presenter=speech_speed_presenter,
        operation_tracker=operation_tracker,
        notifier=notifier,
    )
    view.workflow_controller = workflow_module.controller_for
    view.execute_action = execute_action
    view.actions = actions
    view.speech_coordinator = speech_coordinator
    runtime = AppRuntime(
        shortcuts=shortcuts,
        view=view,
        supervisor=supervisor,
        provider_execution=provider_execution,
        workflows=workflow_module,
        result_output=output_module,
        provider_configuration=provider_module,
        action_feedback=action_feedback_module,
        user_preferences=user_preferences_module,
        hotkey_registrar=lambda _map, _callback: listener,
        tray_factory=Tray if with_tray else None,
        operation_tracker=operation_tracker,
        entry_panel=entry_panel,
    )
    runtime_holder.append(runtime)
    runtime._provider_backend = backend
    return runtime, view, supervisor, outputs, listener


def workflow(view: FakeView, workflow_id: str):
    controller = view.workflow_controller(workflow_id)
    assert controller is not None
    return controller


def test_contextual_question_captures_source_before_first_provider_request() -> None:
    runtime, view, supervisor, _outputs, _listener = make_runtime()

    runtime.enqueue(OpenContextualQuestion())
    runtime.drain_commands()
    controller = workflow(view, view.snapshots[-1].session_id)
    capture_id = controller.snapshot.contextual_source_capture_id

    assert capture_id is not None
    assert view.execute_action.follow_ups == []
    supervisor.work[f"context-source:{capture_id}"]()
    runtime.drain_commands()

    assert controller.snapshot.status is SessionStatus.CONTEXT_QUESTION
    assert controller.snapshot.contextual_source_text == "fixed selected source"
    assert controller.snapshot.source_preview == "Selection: fixed selected source"
    assert view.execute_action.follow_ups == []


def test_contextual_question_first_submit_uses_fixed_source_then_follow_up_history() -> None:
    runtime, view, supervisor, _outputs, _listener = make_runtime()
    runtime.enqueue(OpenContextualQuestion())
    runtime.drain_commands()
    controller = workflow(view, view.snapshots[-1].session_id)
    capture_id = controller.snapshot.contextual_source_capture_id
    assert capture_id is not None
    supervisor.work[f"context-source:{capture_id}"]()
    runtime.drain_commands()
    workflow_id = controller.snapshot.session_id

    runtime.enqueue(SubmitContextualQuestion(workflow_id, "What does this mean?"))
    runtime.drain_commands()
    first_invocation_id = controller.snapshot.active_invocation_id
    assert first_invocation_id is not None
    assert len([key for key in supervisor.work if not key.startswith("context-source:")]) == 1
    supervisor.work[first_invocation_id]()
    first_continuation = view.execute_action.follow_ups[-1][0][0]
    assert first_continuation.question == "What does this mean?"

    first_invocation = view.execute_action.follow_ups[-1][0][1]
    controller.complete(
        first_invocation,
        first_continuation.action,
        first_continuation.input_document(workflow_id),
        "First answer",
        ("follow_up",),
    )
    assert controller.snapshot.source_preview == "Selection: fixed selected source"
    runtime.enqueue(FollowUp(workflow_id, "And why?"))
    runtime.drain_commands()
    second_invocation_id = controller.snapshot.active_invocation_id
    assert second_invocation_id is not None
    supervisor.work[second_invocation_id]()
    second_continuation = view.execute_action.follow_ups[-1][0][0]
    request = second_continuation.build_request(
        default_system_prompt="",
        action_system_prompt=lambda: "",
        model="model",
        default_temperature=0.2,
    )

    assert [message.content for message in request.messages[1:]] == [
        "<source_context>\nfixed selected source\n</source_context>",
        "What does this mean?",
        "First answer",
        "And why?",
    ]


def test_contextual_question_failure_closes_draft_and_reports_clear_error() -> None:
    notifier = Notifier()
    runtime, view, supervisor, _outputs, _listener = make_runtime(notifier=notifier)

    def missing(_cancellation=None):
        raise InputError("找不到文字。")

    runtime._workflow_module._input_resolver.resolve_text = missing
    runtime.enqueue(OpenContextualQuestion())
    runtime.drain_commands()
    workflow_id = view.snapshots[-1].session_id
    controller = workflow(view, workflow_id)
    capture_id = controller.snapshot.contextual_source_capture_id
    assert capture_id is not None
    supervisor.work[f"context-source:{capture_id}"]()
    runtime.drain_commands()

    assert runtime._workflow_module.controller_for(workflow_id) is None
    assert notifier.messages[-1][0] == "ClipAI"
    assert "找不到文字" in notifier.messages[-1][1]


def test_contextual_shortcut_on_focused_result_opens_existing_composer_only() -> None:
    runtime, view, supervisor, _outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    controller = workflow(view, view.snapshots[-1].session_id)
    invocation_id = controller.snapshot.active_invocation_id
    assert invocation_id is not None
    supervisor.work[invocation_id]()
    invocation = view.execute_action.invocations[-1]
    controller.complete(
        invocation,
        view.actions.resolve("a", "short"),
        InputDocument("source", "selection"),
        "answer",
        ("follow_up",),
    )
    workflow_id = controller.snapshot.session_id
    runtime.enqueue(ActivateWorkflow(workflow_id))
    runtime.drain_commands()
    before_revision = controller.snapshot.question_composer_revision
    before_capture_tasks = {key for key in supervisor.work if key.startswith("context-source:")}

    runtime.enqueue(OpenContextualQuestion())
    runtime.drain_commands()

    assert controller.snapshot.question_composer_revision == before_revision + 1
    assert {key for key in supervisor.work if key.startswith("context-source:")} == before_capture_tasks
    assert controller.snapshot.active_invocation_id is None


def test_missing_personal_style_stops_before_workflow_and_provider_execution() -> None:
    notifier = Notifier()
    runtime, view, supervisor, _outputs, _listener = make_runtime(
        notifier=notifier,
        personal_styles=MissingPersonalStyles(),
    )

    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()

    assert view.execute_action.invocations == []
    assert view.snapshots == []
    assert supervisor.work == {}
    assert notifier.messages == [
        ("ClipAI", "尚未選擇個人風格。 Open Personal Styles from the tray menu."),
    ]


def test_contextual_personal_style_actions_keep_the_workflow_profile_snapshot() -> None:
    styles = SwitchingPersonalStyles()
    runtime, view, supervisor, _outputs, _listener = make_runtime(personal_styles=styles)
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    workflow_id = view.snapshots[-1].session_id
    controller = workflow(view, workflow_id)
    first_invocation = controller.snapshot.active_invocation_id
    assert first_invocation is not None
    supervisor.work[first_invocation]()
    step = WorkflowStep("step-1", "a", "Action", "input", "result", "plain_text")
    controller._snapshot = controller.snapshot.evolve(
        status=SessionStatus.COMPLETED,
        content=step.result_text,
        steps=(step,),
        displayed_step_index=0,
        active_invocation_id=None,
    )
    view.context = ActiveWorkflowContext(workflow_id, step.step_id, step.result_text)
    styles.active = PersonalStyleProfile("second", "Second", "second voice", "hash-second")

    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    second_invocation = controller.snapshot.active_invocation_id
    assert second_invocation is not None
    supervisor.work[second_invocation]()

    assert [item.personal_style.profile_id for item in view.execute_action.actions] == ["first", "first"]


def test_output_submit_failure_settles_pending_and_releases_interruption_lease() -> None:
    runtime, view, _supervisor, _outputs, _listener = make_runtime(
        submit_error=RuntimeError("task supervisor is closed")
    )
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    workflow_id = view.snapshots[-1].session_id
    controller = workflow(view, workflow_id)
    controller._snapshot = controller.snapshot.evolve(content="copy me")

    runtime.enqueue(CopyResult(workflow_id, operation_id="copy-op-1"))
    runtime.drain_commands()

    assert [result.state for result in view.output_results[-2:]] == ["pending", "failed"]
    assert all(
        operation.operation_id != "copy-op-1"
        for operation in runtime._user_control.interrupt_current().operations
    )


def test_push_to_talk_invoked_event_never_reaches_the_action_shortcut_resolver() -> None:
    runtime, view, _supervisor, _outputs, _listener = make_runtime(include_voice_input=True)

    runtime.enqueue(ShortcutPressInvoked(ShortcutPressId(1), "voice_input", "long"))
    runtime.drain_commands()

    assert view.snapshots == []


class FakeActionFeedback:
    def __init__(self) -> None:
        self.calls = []

    def record(self, workflow_id, step, command) -> None:
        self.calls.append((workflow_id, step, command))


class GuidanceStore:
    def __init__(self, preferences=None, error=None) -> None:
        self.preferences = preferences or UserPreferences()
        self.error = error

    def load(self):
        return self.preferences

    def save(self, preferences) -> None:
        if self.error:
            raise self.error
        self.preferences = preferences


def test_guidance_setting_waits_for_persistence_before_changing_checked_state() -> None:
    coordinator = UserPreferencesCoordinator(GuidanceStore(UserPreferences(True)))
    presenter = Tray(lambda: None)
    runtime, _view, supervisor, _outputs, _listener = make_runtime(
        guidance_preferences=coordinator,
        guidance_preferences_presenter=presenter,
    )

    runtime.enqueue(SetFirstUseHintsEnabled(False, "guidance-1"))
    runtime.drain_commands()
    assert presenter.guidance_preferences[-1] == GuidancePreferences(True, update_pending=True)

    supervisor.work["guidance-preferences:guidance-1"]()
    runtime.drain_commands()
    assert presenter.guidance_preferences[-1] == GuidancePreferences(False)


def test_reset_guidance_keeps_global_switch_and_only_clears_seen_actions() -> None:
    coordinator = UserPreferencesCoordinator(GuidanceStore(UserPreferences(False, frozenset({"shorten"}))))
    presenter = Tray(lambda: None)
    runtime, _view, supervisor, _outputs, _listener = make_runtime(
        guidance_preferences=coordinator,
        guidance_preferences_presenter=presenter,
    )

    runtime.enqueue(ResetFirstUseHints("reset-1"))
    runtime.drain_commands()
    supervisor.work["guidance-preferences:reset-1"]()
    runtime.drain_commands()

    assert presenter.guidance_preferences[-1] == GuidancePreferences(False)


def test_speech_speed_waits_for_persistence_before_changing_checked_state() -> None:
    coordinator = UserPreferencesCoordinator(GuidanceStore(UserPreferences()), base_speech_rate="+0%")
    presenter = Tray(lambda: None)
    runtime, _view, supervisor, _outputs, _listener = make_runtime(
        guidance_preferences=coordinator,
        guidance_preferences_presenter=presenter,
        speech_speed_presenter=presenter,
    )

    runtime.enqueue(SetSpeechSpeed("super_fast", "speed-1"))
    runtime.drain_commands()
    assert presenter.speech_speeds[-1].selected_speed == "normal"
    assert presenter.speech_speeds[-1].pending_speed == "super_fast"

    supervisor.work["speech-speed-preferences:speed-1"]()
    runtime.drain_commands()
    assert presenter.speech_speeds[-1].selected_speed == "super_fast"
    assert presenter.speech_speeds[-1].pending_speed is None


def test_speech_speed_save_failure_restores_selection_and_marks_tray_error() -> None:
    coordinator = UserPreferencesCoordinator(
        GuidanceStore(UserPreferences(), error=OSError("read only")),
        base_speech_rate="+0%",
    )
    presenter = Tray(lambda: None)
    operations = OperationTracker()
    runtime, _view, supervisor, _outputs, _listener = make_runtime(
        operation_tracker=operations,
        guidance_preferences=coordinator,
        speech_speed_presenter=presenter,
    )

    runtime.enqueue(SetSpeechSpeed("fast", "speed-1"))
    runtime.drain_commands()
    supervisor.work["speech-speed-preferences:speed-1"]()
    runtime.drain_commands()

    assert presenter.speech_speeds[-1].selected_speed == "normal"
    assert presenter.speech_speeds[-1].update_pending is False
    assert operations.events[-1][0] == "report_error"


def test_feedback_is_typed_supervised_work_and_projects_real_completion() -> None:
    feedback = FakeActionFeedback()
    runtime, view, supervisor, _outputs, _listener = make_runtime(action_feedback=feedback)
    runtime.enqueue(StartAction("shorten", "short"))
    runtime.drain_commands()
    workflow_id = view.snapshots[-1].session_id
    controller = workflow(view, workflow_id)
    invocation_id = controller.snapshot.active_invocation_id
    assert invocation_id is not None
    supervisor.work[invocation_id]()
    invocation = view.execute_action.invocations[-1]
    action = view.actions.resolve("shorten", "short")
    controller.complete(
        invocation,
        action,
        InputDocument("private input", "selection"),
        "result",
        ("copy",),
    )

    runtime.enqueue(SubmitActionFeedback(
        workflow_id, invocation_id, "feedback-1", "needs_adjustment", "meaning_lost", "note", True
    ))
    runtime.drain_commands()

    assert controller.snapshot.feedback_state == "pending"
    supervisor.work["action-feedback:feedback-1"]()
    runtime.drain_commands()
    assert controller.snapshot.feedback_state == "succeeded"
    assert feedback.calls[0][1].input_text == "private input"


def test_model_selection_persists_before_switching_new_workflows() -> None:
    preferences = ModelPreferences()
    runtime, view, supervisor, _outputs, _listener = make_runtime(model_preferences=preferences)
    presenter = Tray(lambda: None)
    runtime._model_selection_presenter = presenter
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    first_id = view.snapshots[-1].session_id
    first_work = supervisor.work[workflow(view, first_id).snapshot.active_invocation_id]
    runtime.enqueue(SelectProviderModel("openai", "new-model"))
    runtime.drain_commands()
    first_work()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    second_id = view.snapshots[-1].session_id
    supervisor.work[workflow(view, second_id).snapshot.active_invocation_id]()
    assert preferences.saved == [("OPENAI_MODEL", "new-model")]
    assert view.execute_action.models == ["model", "new-model"]
    assert presenter.model_selections[-1] == ModelSelectionState("openai", ("model", "new-model"), "new-model")


def test_workflow_captures_provider_binding_before_runtime_switch() -> None:
    runtime, view, supervisor, _outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    first_id = view.snapshots[-1].session_id
    first_work = supervisor.work[workflow(view, first_id).snapshot.active_invocation_id]

    replacement = ProviderExecutionBinding(FakeProvider("replacement"), "gemini", "gemini-model")
    runtime._provider_backend.snapshot = ProviderRuntimeSnapshot(
        "gemini",
        (runtime._provider_configuration.active_binding, replacement),
        (
            ProviderOption("openai", "OpenAI", ("model",), "model", True),
            ProviderOption("gemini", "Gemini", ("gemini-model",), "gemini-model", True),
        ),
    )
    runtime._provider_configuration.reload()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    second_id = view.snapshots[-1].session_id
    second_work = supervisor.work[workflow(view, second_id).snapshot.active_invocation_id]

    first_work()
    second_work()
    assert [(item.provider_id, item.model) for item in view.execute_action.bindings] == [
        ("openai", "model"),
        ("gemini", "gemini-model"),
    ]


def test_follow_up_keeps_workflow_provider_binding_after_runtime_switch() -> None:
    runtime, view, supervisor, _outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    workflow_id = view.snapshots[-1].session_id
    controller = workflow(view, workflow_id)
    supervisor.work[controller.snapshot.active_invocation_id]()
    invocation = view.execute_action.invocations[-1]
    action = view.actions.resolve("a", "short")
    controller.complete(
        invocation,
        action,
        InputDocument("input", "selection"),
        "first result",
        ("follow_up",),
    )

    replacement = ProviderExecutionBinding(FakeProvider("replacement"), "gemini", "gemini-model")
    runtime._provider_backend.snapshot = ProviderRuntimeSnapshot(
        "gemini",
        (runtime._provider_configuration.active_binding, replacement),
        (
            ProviderOption("openai", "OpenAI", ("model",), "model", True),
            ProviderOption("gemini", "Gemini", ("gemini-model",), "gemini-model", True),
        ),
    )
    runtime._provider_configuration.reload()

    runtime.enqueue(FollowUp(workflow_id, "What changed?"))
    runtime.drain_commands()
    supervisor.work[controller.snapshot.active_invocation_id]()

    binding = view.execute_action.follow_ups[-1][1]["binding"]
    assert (binding.provider_id, binding.model) == ("openai", "model")


def test_model_selection_write_failure_keeps_previous_model() -> None:
    operations = OperationTracker()
    runtime, _view, _supervisor, _outputs, _listener = make_runtime(
        operation_tracker=operations,
        model_preferences=ModelPreferences(OSError("denied")),
    )
    presenter = Tray(lambda: None)
    runtime._model_selection_presenter = presenter
    runtime.enqueue(SelectProviderModel("openai", "new-model"))
    runtime.drain_commands()
    assert runtime._provider_configuration.active_binding.model == "model"
    assert presenter.model_selections[-1].selected_model == "model"
    assert operations.events[-1][0] == "report_error"


def test_provider_selection_persists_before_switching_new_workflows() -> None:
    preferences = ModelPreferences()
    runtime, _view, _supervisor, _outputs, _listener = make_runtime(model_preferences=preferences)
    presenter = Tray(lambda: None)
    runtime._provider_selection_presenter = presenter
    runtime._model_selection_presenter = presenter
    runtime.enqueue(SelectProvider("gemini"))
    runtime.drain_commands()
    assert preferences.saved == [("CLIPAI_PROVIDER", "gemini")]
    assert runtime._provider_configuration.active_binding.provider_id == "gemini"
    assert presenter.provider_selections[-1].selected_provider == "gemini"
    assert presenter.model_selections[-1] == ModelSelectionState("gemini", ("gemini-model",), "gemini-model")


def test_reload_failure_keeps_previous_provider() -> None:
    operations = OperationTracker()
    runtime, _view, _supervisor, _outputs, _listener = make_runtime(
        operation_tracker=operations,
        reload_provider_settings=lambda: (_ for _ in ()).throw(ValueError("bad env")),
    )
    presenter = Tray(lambda: None)
    runtime._provider_selection_presenter = presenter
    runtime.enqueue(ReloadConfiguration())
    runtime.drain_commands()
    assert runtime._provider_configuration.active_binding.provider_id == "openai"
    assert operations.events[-1][0] == "report_error"


def test_reload_success_replaces_catalog_and_active_binding() -> None:
    option = ProviderOption("gemini", "Gemini", ("fresh",), "fresh", True)
    binding = ProviderExecutionBinding(FakeProvider(), "gemini", "fresh")
    runtime, _view, _supervisor, _outputs, _listener = make_runtime(
        reload_provider_settings=lambda: ProviderRuntimeSnapshot("gemini", (binding,), (option,)),
    )
    presenter = Tray(lambda: None)
    runtime._provider_selection_presenter = presenter
    runtime._model_selection_presenter = presenter
    runtime.enqueue(ReloadConfiguration())
    runtime.drain_commands()
    assert runtime._provider_configuration.active_binding.provider_id == "gemini"
    assert runtime._provider_configuration.active_binding.model == "fresh"
    assert presenter.provider_selections[-1].selected_provider == "gemini"
    assert presenter.provider_selections[-1].providers[0].available_models == ("fresh", "gemini-model")


def test_provider_without_key_is_rejected_without_persistence() -> None:
    preferences = ModelPreferences()
    operations = OperationTracker()
    runtime, _view, _supervisor, _outputs, _listener = make_runtime(
        model_preferences=preferences,
        operation_tracker=operations,
    )
    old = runtime._provider_backend.snapshot
    runtime._provider_backend.snapshot = ProviderRuntimeSnapshot(
        old.active_provider,
        (old.bindings[0], ProviderExecutionBinding(FakeProvider(), "gemini", "gemini-model", (ReadinessIssue("missing", "missing", "llm"),))),
        old.options,
    )
    presenter = Tray(lambda: None)
    runtime._provider_selection_presenter = presenter
    runtime.enqueue(SelectProvider("gemini"))
    runtime.drain_commands()
    assert preferences.saved == []
    assert runtime._provider_configuration.active_binding.provider_id == "openai"
    assert operations.events[-1][0] == "report_error"
    assert runtime._view.provider_settings_states[-1].selected_provider == "gemini"


def test_provider_settings_validate_then_save_and_activate() -> None:
    preferences = ModelPreferences()
    validated: list[tuple[str, str]] = []
    option = ProviderOption("gemini", "Gemini", ("gemini-model",), "gemini-model", True)
    binding = ProviderExecutionBinding(FakeProvider(), "gemini", "gemini-model")
    candidate = ProviderRuntimeSnapshot("gemini", (binding,), (option,))
    runtime, view, supervisor, _outputs, _listener = make_runtime(
        model_preferences=preferences,
        validate_provider_credential=lambda provider, key, _base_url, _model: validated.append((provider, key)),
        build_provider_candidate=lambda _provider, _model, _key, _name, _base_url: candidate,
    )
    command = ValidateAndSaveProviderSettings(ProviderSettingsInput("gemini", "gemini-model", "top-secret"), "save-1")
    assert "top-secret" not in repr(command)
    runtime.enqueue(command)
    runtime.drain_commands()
    assert view.provider_settings_states[-1].operation_state == "pending"
    supervisor.work["provider-settings:save-1"]()
    runtime.drain_commands()
    assert validated == [("gemini", "top-secret")]
    assert preferences.saved == [
        ("CLIPAI_PROVIDER", "gemini"),
        ("GEMINI_API_KEY", "top-secret"),
        ("GEMINI_MODEL", "gemini-model"),
    ]
    assert runtime._provider_configuration.active_binding.provider_id == "gemini"
    assert view.provider_settings_states[-1].operation_state == "succeeded"


def test_provider_settings_operation_gate_rejects_overlapping_save() -> None:
    runtime, view, supervisor, _outputs, _listener = make_runtime(
        model_preferences=ModelPreferences(),
        validate_provider_credential=lambda _provider, _key, _base_url, _model: (_ for _ in ()).throw(RuntimeError("failed")),
        build_provider_candidate=lambda _provider, _model, _key, _name, _base_url: (_ for _ in ()).throw(AssertionError()),
    )
    runtime.enqueue(ValidateAndSaveProviderSettings(ProviderSettingsInput("gemini", "gemini-model", "first"), "old"))
    runtime.drain_commands()
    runtime.enqueue(ValidateAndSaveProviderSettings(ProviderSettingsInput("gemini", "gemini-model", "second"), "new"))
    runtime.drain_commands()
    assert "provider-settings:new" not in supervisor.work
    assert view.provider_settings_states[-1].operation_id == "old"
    supervisor.work["provider-settings:old"]()
    runtime.drain_commands()
    assert view.provider_settings_states[-1].operation_state == "failed"


def test_gateway_settings_allow_empty_key_and_save_single_profile() -> None:
    preferences = ModelPreferences()
    validated = []
    capabilities = ProviderCapabilities(True, True, True, True)
    option = ProviderOption("gateway", "Local AI", ("local-model",), "local-model", True, capabilities=capabilities)
    binding = ProviderExecutionBinding(FakeProvider(), "gateway", "local-model")
    candidate = ProviderRuntimeSnapshot("gateway", (binding,), (option,), "Local AI", "http://localhost:8000/v1")
    runtime, view, supervisor, _outputs, _listener = make_runtime(
        model_preferences=preferences,
        validate_provider_credential=lambda provider, key, base_url, model: validated.append((provider, key, base_url, model)),
        build_provider_candidate=lambda _provider, _model, _key, _name, _base_url: candidate,
    )
    old = runtime._provider_backend.snapshot
    runtime._provider_backend.snapshot = ProviderRuntimeSnapshot(
        old.active_provider,
        (*old.bindings, ProviderExecutionBinding(FakeProvider(), "gateway", "")),
        (*old.options, ProviderOption("gateway", "Custom Gateway", (), "", False, capabilities=capabilities)),
    )
    runtime._provider_configuration.reload()
    command = ValidateAndSaveProviderSettings(
        ProviderSettingsInput("gateway", "local-model", "", "Local AI", "http://localhost:8000"),
        "gateway-save",
    )
    secret_url_command = ValidateAndSaveProviderSettings(ProviderSettingsInput("gateway", "model", connection_base_url="https://gateway.test?token=hidden"))
    assert "token=hidden" not in repr(secret_url_command)
    runtime.enqueue(command)
    runtime.drain_commands()
    supervisor.work["provider-settings:gateway-save"]()
    runtime.drain_commands()
    assert validated == [("gateway", "", "http://localhost:8000", "local-model")]
    assert preferences.saved == [
        ("CLIPAI_PROVIDER", "gateway"),
        ("CLIPAI_GATEWAY_NAME", "Local AI"),
        ("CLIPAI_GATEWAY_BASE_URL", "http://localhost:8000"),
        ("CLIPAI_GATEWAY_MODEL", "local-model"),
    ]
    assert runtime._provider_configuration.active_binding.provider_id == "gateway"
    assert view.provider_settings_states[-1].operation_state == "succeeded"


def test_refresh_models_replaces_catalog_but_keeps_current_model() -> None:
    runtime, view, supervisor, _outputs, _listener = make_runtime(
        discover_provider_models=lambda provider, _connection: ("remote-a", "remote-a", "remote-b") if provider == "openai" else (),
    )
    presenter = Tray(lambda: None)
    runtime._model_selection_presenter = presenter
    runtime.enqueue(RefreshProviderModels("openai", "refresh-1"))
    runtime.drain_commands()
    assert presenter.model_selections[-1].refreshing is True
    supervisor.work["provider-models:refresh-1"]()
    runtime.drain_commands()
    assert runtime._provider_configuration.model_selection().available_models == ("model", "remote-a", "remote-b")
    assert presenter.model_selections[-1].refreshing is False
    assert view.provider_settings_states[-1].operation_state == "succeeded"


def test_provider_settings_model_change_keeps_existing_api_key() -> None:
    preferences = ModelPreferences()
    validated = []
    binding = ProviderExecutionBinding(FakeProvider(), "gemini", "gemini-model")
    candidate = ProviderRuntimeSnapshot("gemini", (binding,), (ProviderOption("gemini", "Gemini", ("gemini-model",), "gemini-model", True),))
    runtime, _view, supervisor, _outputs, _listener = make_runtime(
        model_preferences=preferences,
        validate_provider_credential=lambda provider, key, _base_url, _model: validated.append((provider, key)),
        build_provider_candidate=lambda _provider, _model, _key, _name, _base_url: candidate,
    )

    runtime.enqueue(ValidateAndSaveProviderSettings(ProviderSettingsInput("gemini", "gemini-model", ""), "keep-key"))
    runtime.drain_commands()
    supervisor.work["provider-settings:keep-key"]()
    runtime.drain_commands()

    assert validated == [("gemini", "")]
    assert preferences.saved == [("CLIPAI_PROVIDER", "gemini"), ("GEMINI_MODEL", "gemini-model")]


def test_opening_selected_provider_reloads_credential_hint_without_activating_it() -> None:
    openai_option = ProviderOption("openai", "OpenAI", ("model",), "model", True, credential_hint="••••old1")
    gemini_option = ProviderOption("gemini", "Gemini", ("gemini-model",), "gemini-model", True, credential_hint="••••new2")
    snapshot = ProviderRuntimeSnapshot(
        "openai",
        (
            ProviderExecutionBinding(FakeProvider(), "openai", "model"),
            ProviderExecutionBinding(FakeProvider(), "gemini", "gemini-model"),
        ),
        (openai_option, gemini_option),
    )
    runtime, view, _supervisor, _outputs, _listener = make_runtime(reload_provider_settings=lambda: snapshot)

    runtime.enqueue(OpenProviderSettings("gemini"))
    runtime.drain_commands()

    state = view.provider_settings_states[-1]
    selected = next(item for item in state.providers if item.provider_id == "gemini")
    assert state.selected_provider == "gemini"
    assert selected.credential_hint == "••••new2"
    assert runtime._provider_configuration.active_binding.provider_id == "openai"


def test_provider_switch_reloads_binding_before_activation() -> None:
    preferences = ModelPreferences()
    refreshed = ProviderExecutionBinding(FakeProvider(), "gemini", "fresh-model")
    snapshot = ProviderRuntimeSnapshot(
        "openai",
        (
            ProviderExecutionBinding(FakeProvider(), "openai", "model"),
            refreshed,
        ),
        (
            ProviderOption("openai", "OpenAI", ("model",), "model", True),
            ProviderOption("gemini", "Gemini", ("fresh-model",), "fresh-model", True, credential_hint="••••new2"),
        ),
    )
    runtime, _view, _supervisor, _outputs, _listener = make_runtime(
        model_preferences=preferences,
        reload_provider_settings=lambda: snapshot,
    )
    presenter = Tray(lambda: None)
    runtime._provider_selection_presenter = presenter
    runtime._model_selection_presenter = presenter

    runtime.enqueue(SelectProvider("gemini"))
    runtime.drain_commands()

    assert runtime._provider_configuration.active_binding is refreshed
    assert runtime._provider_configuration.active_binding.model == "fresh-model"


def test_gateway_refresh_uses_unsaved_connection_without_writing_settings() -> None:
    preferences = ModelPreferences()
    received = []
    runtime, _view, supervisor, _outputs, _listener = make_runtime(
        model_preferences=preferences,
        discover_provider_models=lambda provider, connection: received.append((provider, connection)) or ("gateway-a", "gateway-b"),
    )
    old = runtime._provider_backend.snapshot
    runtime._provider_backend.snapshot = ProviderRuntimeSnapshot(
        old.active_provider,
        (*old.bindings, ProviderExecutionBinding(FakeProvider(), "gateway", "")),
        (*old.options, ProviderOption("gateway", "Gateway", (), "", False)),
    )
    runtime._provider_configuration.reload()
    from ClipAI.core.models import ModelCatalogConnection

    runtime.enqueue(RefreshProviderModels("gateway", "gateway-refresh", ModelCatalogConnection("http://localhost:8000", "secret", "fallback")))
    runtime.drain_commands()
    supervisor.work["provider-models:gateway-refresh"]()
    runtime.drain_commands()

    assert received == [("gateway", ModelCatalogConnection("http://localhost:8000", "secret", "fallback"))]
    assert preferences.saved == []
    option = next(item for item in runtime._provider_configuration.provider_selection().providers if item.provider_id == "gateway")
    assert option.available_models == ("gateway-a", "gateway-b")


def test_refresh_failure_keeps_previous_catalog() -> None:
    runtime, view, supervisor, _outputs, _listener = make_runtime(discover_provider_models=lambda _provider, _connection: ())
    presenter = Tray(lambda: None)
    runtime._model_selection_presenter = presenter
    runtime.enqueue(RefreshProviderModels("openai", "refresh-empty"))
    runtime.drain_commands()
    supervisor.work["provider-models:refresh-empty"]()
    runtime.drain_commands()
    assert runtime._provider_configuration.model_selection().available_models == ("model", "new-model")
    assert view.provider_settings_states[-1].operation_state == "failed"


def test_model_refresh_operation_gate_rejects_overlapping_refresh() -> None:
    runtime, view, supervisor, _outputs, _listener = make_runtime(discover_provider_models=lambda _provider, _connection: ("old-model",))
    runtime.enqueue(RefreshProviderModels("openai", "old-refresh"))
    runtime.drain_commands()
    runtime.enqueue(RefreshProviderModels("openai", "new-refresh"))
    runtime.drain_commands()
    assert "provider-models:new-refresh" not in supervisor.work
    assert view.provider_settings_states[-1].operation_id == "old-refresh"
    supervisor.work["provider-models:old-refresh"]()
    runtime.drain_commands()
    assert runtime._provider_configuration.model_selection().available_models == ("model", "old-model")


def test_gateway_model_selection_uses_clipai_env_name() -> None:
    preferences = ModelPreferences()
    runtime, _view, _supervisor, _outputs, _listener = make_runtime(model_preferences=preferences)
    binding = ProviderExecutionBinding(FakeProvider(), "gateway", "old")
    runtime._provider_backend.snapshot = ProviderRuntimeSnapshot(
        "gateway",
        (binding,),
        (ProviderOption("gateway", "Gateway", ("old", "new"), "old", True),),
    )
    runtime._provider_configuration.reload()
    presenter = Tray(lambda: None)
    runtime._model_selection_presenter = presenter
    runtime.enqueue(SelectProviderModel("gateway", "new"))
    runtime.drain_commands()
    assert preferences.saved == [("CLIPAI_GATEWAY_MODEL", "new")]


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


def test_global_speech_shortcut_replaces_active_speech_with_latest_request() -> None:
    speech = GlobalSpeech()
    runtime, view, supervisor, _outputs, _listener = make_runtime(speech_coordinator=speech)
    runtime.enqueue(ShortcutPressInvoked(ShortcutPressId(1), "speech", "short"))
    runtime.drain_commands()

    runtime.enqueue(ShortcutPressInvoked(ShortcutPressId(2), "speech", "short"))
    runtime.drain_commands()

    assert speech.clipboard_only == [False, False]
    assert speech.cancelled == 1
    assert speech.current_identity == (SpeechJob.operation_id, SpeechJob.workflow_id)
    assert supervisor.cancelled == [SpeechJob.operation_id]
    assert [(result.operation_id, result.state) for result in view.output_results] == [
        (SpeechJob.operation_id, "pending"),
        (SpeechJob.operation_id, "cancelled"),
        (SpeechJob.operation_id, "pending"),
    ]


def test_long_speech_shortcut_keeps_active_speech_and_arms_sequence() -> None:
    speech = GlobalSpeech()
    runtime, _view, _supervisor, _outputs, _listener = make_runtime(speech_coordinator=speech)
    runtime.enqueue(ShortcutPressInvoked(ShortcutPressId(1), "speech", "short"))
    runtime.drain_commands()

    runtime.enqueue(ShortcutPressInvoked(ShortcutPressId(2), "speech", "long"))
    runtime.drain_commands()

    assert speech.current_identity == (SpeechJob.operation_id, SpeechJob.workflow_id)
    assert speech.cancelled == 0
    assert speech.clipboard_only == [False]


def test_global_speech_still_prefers_current_selection_when_session_exists() -> None:
    speech = GlobalSpeech()
    runtime, _view, _supervisor, _outputs, _listener = make_runtime(speech_coordinator=speech)
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    runtime.enqueue(SpeakSelectionOrClipboard())
    runtime.drain_commands()
    assert speech.clipboard_only == [False]


def test_short_escape_stops_current_speech_without_windows_notifications() -> None:
    notifier = Notifier()
    tracker = OperationTracker()
    speech = GlobalSpeech()
    runtime, _view, supervisor, _outputs, _listener = make_runtime(
        notifier=notifier,
        operation_tracker=tracker,
        speech_coordinator=speech,
    )
    runtime.enqueue(SpeakSelectionOrClipboard())
    runtime.drain_commands()

    runtime.enqueue(InterruptionRequested("current"))
    runtime.drain_commands()

    assert speech.current_identity is None
    assert f"speech:{SpeechJob.operation_id}" in supervisor.cancelled
    assert notifier.messages == []
    assert ("cancel", f"tts:{SpeechJob.operation_id}") in tracker.events


def test_short_escape_uses_latest_operation_without_stopping_older_workflow() -> None:
    speech = GlobalSpeech()
    runtime, view, _supervisor, _outputs, _listener = make_runtime(speech_coordinator=speech)
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    workflow_id = view.snapshots[-1].session_id
    invocation_id = workflow(view, workflow_id).snapshot.active_invocation_id
    runtime.enqueue(SpeakSelectionOrClipboard())
    runtime.drain_commands()

    runtime.enqueue(InterruptCurrent())
    runtime.drain_commands()

    assert speech.current_identity is None
    assert workflow(view, workflow_id).snapshot.active_invocation_id == invocation_id


def test_short_escape_closes_focused_popup_without_stopping_unowned_speech() -> None:
    speech = GlobalSpeech()
    runtime, view, _supervisor, _outputs, _listener = make_runtime(speech_coordinator=speech)
    runtime.enqueue(SpeakSelectionOrClipboard())
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    workflow_id = view.snapshots[-1].session_id
    runtime.enqueue(ActivateWorkflow(workflow_id))
    runtime.enqueue(InterruptCurrent())
    runtime.drain_commands()

    assert runtime._workflow_module.controller_for(workflow_id) is None
    assert speech.current_identity == (SpeechJob.operation_id, SpeechJob.workflow_id)


def test_pinned_workflow_reuses_the_same_popup_for_a_new_visible_action() -> None:
    runtime, view, supervisor, _outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    pinned_id = view.snapshots[-1].session_id
    pinned = workflow(view, pinned_id)
    pinned._snapshot = pinned.snapshot.evolve(
        status=SessionStatus.COMPLETED,
        content="keep me",
        pinned=True,
        active_invocation_id=None,
    )
    prior_task_ids = set(supervisor.work)

    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()

    assert view.workflow_controller(pinned_id) is pinned
    assert pinned.snapshot.content == "keep me"
    assert pinned.snapshot.pinned is True
    assert pinned.snapshot.active_invocation_id is not None
    assert pinned.snapshot.active_invocation_id not in prior_task_ids
    assert pinned.snapshot.active_invocation_id in supervisor.work
    assert len({snapshot.session_id for snapshot in view.snapshots}) == 1
    assert view.attentions == []


def test_unfocused_pinned_workflow_requires_explicit_focus_for_voice_input() -> None:
    runtime, view, _supervisor, _outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    workflow_id = view.snapshots[-1].session_id
    runtime.enqueue(TogglePin(workflow_id))
    runtime.drain_commands()
    pinned = workflow(view, workflow_id)
    invocation_id = pinned.snapshot.active_invocation_id
    assert invocation_id is not None

    rejected = runtime._workflow_module.admit_voice_capture(VoiceCaptureIntent("shortcut"))
    continued = runtime._workflow_module.admit_voice_capture(
        VoiceCaptureIntent("shortcut", active_voice_workflow_id=workflow_id)
    )

    assert rejected.kind == "rejected"
    assert rejected.workflow_id == workflow_id
    assert "點選目前的 ClipAI 視窗" in rejected.message
    assert continued.kind == "continue"
    assert continued.workflow_id == workflow_id
    assert runtime._workflow_module.controller_for(workflow_id) is pinned
    assert pinned.snapshot.pinned is True
    assert pinned.snapshot.active_invocation_id == invocation_id
    assert invocation_id not in _supervisor.cancelled


def test_focused_completed_result_routes_voice_input_to_follow_up() -> None:
    runtime, view, _supervisor, _outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    workflow_id = view.snapshots[-1].session_id
    controller = workflow(view, workflow_id)
    step = WorkflowStep("step-1", "a", "Action", "input", "answer", "plain_text")
    controller._snapshot = controller.snapshot.evolve(
        status=SessionStatus.COMPLETED,
        content="answer",
        available_actions=("copy", "follow_up"),
        steps=(step,),
        displayed_step_index=0,
        active_invocation_id=None,
    )

    admission = runtime._workflow_module.admit_voice_capture(VoiceCaptureIntent(
        "shortcut",
        focused_surface=ControlSurfaceRef(workflow_id, "workflow"),
    ))

    assert admission.kind == "follow_up"
    assert admission.workflow_id == workflow_id
    assert admission.target == VoiceFollowUpTarget(workflow_id)


def test_open_voice_follow_up_routes_ptt_to_follow_up_instead_of_the_draft() -> None:
    class VoiceSurface:
        def voice_capture_surface_context(self, workflow_id: str) -> VoiceCaptureSurfaceContext:
            return VoiceCaptureSurfaceContext(workflow_id, follow_up_requested=True, selection=(0, 0))

    runtime, _view, _supervisor, _outputs, _listener = make_runtime()
    workflow_id = "voice-workflow"
    controller = runtime._workflow_module.create_voice_workflow(
        workflow_id,
        PasteTarget("hwnd:10", 42, "Notepad", "Untitled", 1),
    )
    controller._snapshot = controller.snapshot.evolve(
        status=SessionStatus.VOICE_REVIEW,
        content="reviewed voice draft",
        available_actions=("copy", "paste", "follow_up"),
    )
    runtime._workflow_module._voice_capture_context_reader = VoiceSurface()

    shortcut_admission = runtime._workflow_module.admit_voice_capture(VoiceCaptureIntent(
        "shortcut",
        focused_surface=ControlSurfaceRef(workflow_id, "workflow"),
    ))
    popup_admission = runtime._workflow_module.admit_voice_capture(
        VoiceCaptureIntent("popup", workflow_id=workflow_id)
    )

    assert shortcut_admission.kind == "follow_up"
    assert shortcut_admission.target == VoiceFollowUpTarget(workflow_id)
    assert popup_admission.kind == "voice_review"
    assert popup_admission.target is not None


@pytest.mark.parametrize(
    (
        "trigger",
        "status",
        "focused",
        "follow_up_requested",
        "available_actions",
        "active_invocation_id",
        "active_capture",
        "expected_kind",
    ),
    (
        pytest.param("shortcut", None, False, False, (), None, False, "create", id="shortcut-creates-without-visible-workflow"),
        pytest.param("popup", None, False, False, (), None, False, "rejected", id="popup-requires-existing-workflow"),
        pytest.param("shortcut", SessionStatus.VOICE_REVIEW, True, False, ("follow_up",), None, False, "voice_review", id="shortcut-continues-voice-review"),
        pytest.param("shortcut", SessionStatus.VOICE_REVIEW, True, True, ("follow_up",), None, False, "follow_up", id="shortcut-honors-follow-up-intent"),
        pytest.param("popup", SessionStatus.VOICE_REVIEW, True, True, ("follow_up",), None, False, "voice_review", id="popup-keeps-voice-review-intent"),
        pytest.param("shortcut", SessionStatus.CONTEXT_QUESTION, True, True, ("follow_up",), None, False, "follow_up", id="shortcut-dictates-contextual-question"),
        pytest.param("popup", SessionStatus.CONTEXT_QUESTION, True, False, ("follow_up",), None, False, "follow_up", id="popup-dictates-contextual-question"),
        pytest.param("shortcut", SessionStatus.COMPLETED, True, False, ("follow_up",), None, False, "follow_up", id="shortcut-continues-completed-result"),
        pytest.param("popup", SessionStatus.COMPLETED, True, False, ("follow_up",), None, False, "follow_up", id="popup-continues-completed-result"),
        pytest.param("shortcut", SessionStatus.FAILED, True, False, ("follow_up",), None, False, "follow_up", id="shortcut-continues-failed-result"),
        pytest.param("popup", SessionStatus.STOPPED, True, False, ("follow_up",), None, False, "follow_up", id="popup-continues-stopped-result"),
        pytest.param("shortcut", SessionStatus.COMPLETED, True, False, ("copy",), None, False, "rejected", id="shortcut-rejects-unavailable-follow-up"),
        pytest.param("popup", SessionStatus.COMPLETED, True, False, ("follow_up",), "provider-1", False, "rejected", id="popup-rejects-active-invocation"),
        pytest.param("shortcut", SessionStatus.REQUESTING_PROVIDER, True, False, ("follow_up",), "provider-1", False, "rejected", id="shortcut-rejects-provider-active"),
        pytest.param("shortcut", SessionStatus.REQUESTING_PROVIDER, True, True, ("follow_up",), "provider-1", False, "rejected", id="shortcut-open-follow-up-does-not-bypass-provider"),
        pytest.param("popup", SessionStatus.REQUESTING_PROVIDER, True, False, ("follow_up",), "provider-1", False, "rejected", id="popup-rejects-provider-active"),
        pytest.param("shortcut", SessionStatus.VOICE_REVIEW, False, False, ("follow_up",), None, False, "rejected", id="shortcut-requires-focused-visible-workflow"),
        pytest.param("shortcut", SessionStatus.VOICE_REVIEW, False, False, ("follow_up",), None, True, "continue", id="shortcut-continues-active-capture"),
    ),
)
def test_voice_capture_destination_admission_matrix(
    trigger,
    status,
    focused,
    follow_up_requested,
    available_actions,
    active_invocation_id,
    active_capture,
    expected_kind,
) -> None:
    class VoiceSurface:
        def voice_capture_surface_context(self, workflow_id: str) -> VoiceCaptureSurfaceContext:
            return VoiceCaptureSurfaceContext(
                workflow_id,
                follow_up_requested=follow_up_requested,
                selection=(0, 0),
            )

    runtime, _view, _supervisor, _outputs, _listener = make_runtime()
    workflow_id = "voice-workflow"
    if status is not None:
        controller = runtime._workflow_module.create_voice_workflow(workflow_id, None)
        steps = (
            (WorkflowStep("step-1", "a", "Action", "input", "answer", "plain_text"),)
            if status in {SessionStatus.COMPLETED, SessionStatus.FAILED, SessionStatus.STOPPED}
            else ()
        )
        controller._snapshot = controller.snapshot.evolve(
            status=status,
            content="reviewed voice draft",
            available_actions=available_actions,
            active_invocation_id=active_invocation_id,
            steps=steps,
            displayed_step_index=0 if steps else -1,
        )
    runtime._workflow_module._voice_capture_context_reader = VoiceSurface()
    intent = VoiceCaptureIntent(
        trigger,
        workflow_id=workflow_id if trigger == "popup" else None,
        focused_surface=(ControlSurfaceRef(workflow_id, "workflow") if focused else None),
        active_voice_workflow_id=(workflow_id if active_capture else None),
    )

    admission = runtime._workflow_module.admit_voice_capture(intent)

    assert admission.kind == expected_kind


def test_voice_review_follow_up_submission_starts_a_voice_draft_provider_request() -> None:
    runtime, view, supervisor, _outputs, _listener = make_runtime(include_voice_input=True)
    workflow_id = "voice-workflow"
    controller = runtime._workflow_module.create_voice_workflow(
        workflow_id,
        PasteTarget("hwnd:10", 42, "Notepad", "Untitled", 1),
    )
    controller._snapshot = controller.snapshot.evolve(
        status=SessionStatus.VOICE_REVIEW,
        content="reviewed voice draft",
        available_actions=("copy", "paste", "follow_up"),
        voice_origin=VoiceOrigin(
            PasteTarget("hwnd:10", 42, "Notepad", "Untitled", 1),
            "reviewed voice draft",
            1,
        ),
    )

    runtime.enqueue(FollowUp(workflow_id, "What should I do next?"))
    runtime.drain_commands()

    invocation_id = controller.snapshot.active_invocation_id
    assert invocation_id is not None
    assert invocation_id in supervisor.work
    supervisor.work[invocation_id]()
    assert len(view.execute_action.follow_ups) == 1
    args, kwargs = view.execute_action.follow_ups[0]
    continuation = args[0]
    assert continuation.question == "What should I do next?"
    assert continuation.action.id == "voice_draft_follow_up"
    assert continuation.input_source == "voice_draft"
    assert continuation.parent_step_id is None
    assert kwargs["binding"] is runtime._workflow_module._records[workflow_id].binding


def test_focused_answering_popup_rejects_a_second_voice_question() -> None:
    runtime, view, _supervisor, _outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    workflow_id = view.snapshots[-1].session_id

    admission = runtime._workflow_module.admit_voice_capture(VoiceCaptureIntent(
        "shortcut",
        focused_surface=ControlSurfaceRef(workflow_id, "workflow"),
    ))

    assert admission.kind == "rejected"
    assert admission.workflow_id == workflow_id
    assert admission.message == "AI 正在回答，完成後再追問。"


def test_focused_result_without_follow_up_does_not_become_a_voice_draft() -> None:
    runtime, view, _supervisor, _outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    workflow_id = view.snapshots[-1].session_id
    controller = workflow(view, workflow_id)
    step = WorkflowStep("step-1", "a", "Action", "input", "answer", "plain_text")
    controller._snapshot = controller.snapshot.evolve(
        status=SessionStatus.COMPLETED,
        content="answer",
        available_actions=("copy",),
        steps=(step,),
        displayed_step_index=0,
        active_invocation_id=None,
    )

    admission = runtime._workflow_module.admit_voice_capture(VoiceCaptureIntent(
        "shortcut",
        focused_surface=ControlSurfaceRef(workflow_id, "workflow"),
    ))

    assert admission.kind == "rejected"
    assert admission.workflow_id == workflow_id
    assert admission.message == "這份內容目前無法使用 Follow-up。"
    assert controller.snapshot.content == "answer"
    assert controller.snapshot.status is SessionStatus.COMPLETED


def test_failed_active_voice_attention_repeats_the_status_through_the_notifier() -> None:
    notifier = Notifier()
    runtime, view, _supervisor, _outputs, _listener = make_runtime(notifier=notifier)
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    workflow_id = view.snapshots[-1].session_id
    admission = runtime._workflow_module.admit_voice_capture(
        VoiceCaptureIntent("shortcut", active_voice_workflow_id=workflow_id)
    )
    assert admission.kind == "continue"
    attention = view.attentions[-1]

    runtime.enqueue(WorkflowAttentionCompleted(attention.attention_id, workflow_id, False))
    runtime.drain_commands()

    assert notifier.messages[-1] == (
        "ClipAI",
        "語音輸入進行中。視窗未取得焦點，請先點選該視窗後再操作。",
    )


def test_global_cancel_stops_pinned_invocation_and_restores_its_completed_content() -> None:
    runtime, view, supervisor, _outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    pinned_id = view.snapshots[-1].session_id
    pinned = workflow(view, pinned_id)
    step = WorkflowStep("step-1", "a", "Action", "input", "keep me", "plain_text")
    pinned._snapshot = pinned.snapshot.evolve(
        status=SessionStatus.REQUESTING_PROVIDER,
        content=step.result_text,
        pinned=True,
        steps=(step,),
        displayed_step_index=0,
        active_invocation_id="pinned-follow-up",
    )

    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    runtime.enqueue(InterruptAll())
    runtime.drain_commands()

    assert "pinned-follow-up" in supervisor.cancelled
    assert pinned.snapshot.status == SessionStatus.COMPLETED
    assert pinned.snapshot.active_invocation_id is None
    assert pinned.snapshot.content == "keep me"


def test_contextual_action_reuses_active_workflow_and_prefers_popup_selection() -> None:
    runtime, view, supervisor, _outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    workflow_id = view.snapshots[-1].session_id
    controller = workflow(view, workflow_id)
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

    assert {snapshot.session_id for snapshot in view.snapshots} == {workflow_id}
    new_invocation = controller.snapshot.active_invocation_id
    assert new_invocation != old_invocation
    supervisor.work[new_invocation]()
    invocation = view.execute_action.invocations[-1]
    assert invocation.input_target.document.text == "selected popup text"
    assert invocation.parent_step_id == "step-1"


def test_start_action_admission_uses_explicit_prepared_input_target() -> None:
    runtime, view, supervisor, _outputs, _listener = make_runtime()
    prepared_target = InputTarget(
        "external_text",
        InputDocument("prepared panel input", "selection"),
    )

    admission = runtime._workflow_module.start_action(
        "a",
        "short",
        input_target=prepared_target,
    )
    runtime.drain_commands()

    assert admission.accepted
    controller = workflow(view, view.snapshots[-1].session_id)
    invocation_id = controller.snapshot.active_invocation_id
    assert invocation_id is not None
    supervisor.work[invocation_id]()
    assert view.execute_action.invocations[-1].input_target is prepared_target


def test_accepted_follow_up_records_its_root_action_as_recent() -> None:
    history = RecentActionHistory()
    persisted = []
    runtime, view, supervisor, _outputs, _listener = make_runtime(
        recent_actions=history,
        recent_action_sink=persisted.append,
    )
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    controller = workflow(view, view.snapshots[-1].session_id)
    root_invocation_id = controller.snapshot.active_invocation_id
    assert root_invocation_id is not None
    supervisor.work[root_invocation_id]()
    root_invocation = view.execute_action.invocations[-1]
    root_action = view.execute_action.actions[-1]
    controller.complete(
        root_invocation,
        root_action,
        InputDocument("source", "selection"),
        "root result",
        ("follow_up",),
    )
    runtime.drain_commands()

    follow_invocation = ActionInvocation(
        "follow-step",
        "shorten",
        "long",
        InputTarget(
            "workflow_result",
            InputDocument("question", "workflow_result", controller.snapshot.session_id, root_invocation_id),
        ),
        workflow_id=controller.snapshot.session_id,
        parent_step_id=root_invocation_id,
    )
    follow_action = view.actions.resolve("shorten", "long")
    controller.begin_invocation(follow_invocation, follow_action)
    controller.complete(
        follow_invocation,
        follow_action,
        follow_invocation.input_target.document,
        "follow result",
        ("follow_up",),
    )
    runtime.drain_commands()

    assert history.refs == (EntryActionRef("a", "short"),)
    assert persisted[-1] == history.refs


def test_new_visible_action_replaces_a_released_unpinned_popup() -> None:
    runtime, view, _supervisor, _outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    hidden_id = view.snapshots[-1].session_id
    controller = workflow(view, hidden_id)
    step = WorkflowStep("step-1", "a", "Action", "input", "hidden result", "plain_text")
    controller._snapshot = controller.snapshot.evolve(
        status=SessionStatus.COMPLETED,
        content=step.result_text,
        steps=(step,),
        displayed_step_index=0,
        active_invocation_id=None,
    )
    view.context = ActiveWorkflowContext(hidden_id, step.step_id, step.result_text, "selected hidden text")

    runtime.enqueue(PasteOperationCompleted(
        "paste-op",
        hidden_id,
        PasteOutcome("dispatched_unconfirmed", "dispatched_unconfirmed", "restored"),
    ))
    runtime.enqueue(StartAction("shorten", "short"))
    runtime.drain_commands()

    workflow_ids = {snapshot.session_id for snapshot in view.snapshots}
    assert len(workflow_ids) == 2
    assert hidden_id in workflow_ids
    assert runtime._workflow_module.controller_for(hidden_id) is None


def test_contextual_action_without_popup_context_creates_external_workflow() -> None:
    runtime, view, _supervisor, _outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("shorten", "short"))
    runtime.drain_commands()
    controller = workflow(view, view.snapshots[-1].session_id)
    assert controller.snapshot.active_invocation_id is not None


def test_speech_sequence_is_headless_and_prefers_popup_selection() -> None:
    runtime, view, supervisor, _outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    popup_id = view.snapshots[-1].session_id
    controller = workflow(view, popup_id)
    step = WorkflowStep("step-1", "a", "Action", "input", "full popup result", "plain_text")
    controller._snapshot = controller.snapshot.evolve(
        status=SessionStatus.COMPLETED,
        content=step.result_text,
        steps=(step,),
        displayed_step_index=0,
        active_invocation_id=None,
    )
    view.context = ActiveWorkflowContext(popup_id, step.step_id, step.result_text, "selected popup text")
    rendered_before = len(view.snapshots)

    runtime.enqueue(StartAction("a", "short", "speech"))
    runtime.drain_commands()
    speech_invocation_id = next(reversed(supervisor.work))
    supervisor.work[speech_invocation_id]()

    invocation = view.execute_action.invocations[-1]
    assert invocation.result_route == "speech"
    assert invocation.input_target.document.text == "selected popup text"
    assert len(view.snapshots) == rendered_before


def test_latest_start_cancels_previous_unpinned_session() -> None:
    runtime, view, supervisor, _outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    first_id = view.snapshots[-1].session_id
    first_invocation = workflow(view, first_id).snapshot.active_invocation_id
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    assert first_invocation in supervisor.cancelled
    assert any(s.session_id == first_id and s.status == SessionStatus.CANCELLED for s in view.snapshots)


def test_cancel_ends_workflow_and_repeated_cancel_is_idempotent() -> None:
    runtime, view, supervisor, _outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    workflow_id = view.snapshots[-1].session_id
    controller = workflow(view, workflow_id)
    invocation_id = controller.snapshot.active_invocation_id

    runtime.enqueue(CancelSession(workflow_id))
    runtime.enqueue(CancelSession(workflow_id))
    runtime.drain_commands()

    assert controller.snapshot.status == SessionStatus.CANCELLED
    assert view.workflow_controller(workflow_id) is None
    assert supervisor.cancelled.count(invocation_id) == 1


def test_pinned_workflow_ignores_stale_activation_and_reuses_its_popup() -> None:
    runtime, view, _supervisor, _outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    first_id = view.snapshots[-1].session_id
    runtime.enqueue(TogglePin(first_id))
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    runtime.enqueue(ActivateWorkflow("already-ended"))
    runtime.enqueue(StartAction("shorten", "short"))
    runtime.drain_commands()

    assert view.workflow_controller(first_id) is not None
    assert len({snapshot.session_id for snapshot in view.snapshots}) == 1
    assert workflow(view, first_id).snapshot.action_id == "shorten"
    assert workflow(view, first_id).snapshot.active_invocation_id is not None
    assert view.attentions == []


def test_pinned_workflow_remains_the_only_activation_candidate() -> None:
    runtime, view, _supervisor, _outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    pinned_id = view.snapshots[-1].session_id
    runtime.enqueue(TogglePin(pinned_id))
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    assert runtime._workflow_module.controller_for(pinned_id) is not None
    assert runtime._workflow_module.has_foreground_workflow() is True


def test_direct_headless_actions_do_not_form_a_global_singleton() -> None:
    runtime, _view, supervisor, _outputs, _listener = make_runtime()

    runtime.enqueue(StartAction("a", "short", "speech"))
    runtime.enqueue(StartAction("a", "short", "speech"))
    runtime.drain_commands()

    assert len(supervisor.work) == 2
    assert supervisor.cancelled == []


def test_headless_workflow_cannot_be_activated(monkeypatch) -> None:
    class FixedIdentity:
        hex = "headless-workflow"

    monkeypatch.setattr("ClipAI.app.runtime_workflows.uuid.uuid4", lambda: FixedIdentity())
    runtime, _view, _supervisor, _outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short", "speech"))
    runtime.enqueue(ActivateWorkflow("headless-workflow"))
    runtime.drain_commands()

    assert runtime._workflow_module.has_foreground_workflow() is False


def test_pinned_workflow_reuse_prevents_duplicate_visible_workflow_admission(monkeypatch) -> None:
    class FixedIdentity:
        hex = "duplicate-workflow"

    monkeypatch.setattr("ClipAI.app.runtime_workflows.uuid.uuid4", lambda: FixedIdentity())
    runtime, view, _supervisor, _outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    runtime.enqueue(TogglePin("duplicate-workflow"))
    runtime.drain_commands()

    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()

    assert view.workflow_controller("duplicate-workflow") is not None
    assert len({snapshot.session_id for snapshot in view.snapshots}) == 1
    assert view.attentions == []


def test_visible_submission_failure_remains_as_failed_workflow() -> None:
    runtime, view, _supervisor, _outputs, _listener = make_runtime(
        submit_error=RuntimeError("supervisor closed"),
    )

    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()

    workflow_id = view.snapshots[-1].session_id
    assert view.snapshots[-1].status == SessionStatus.FAILED
    assert view.workflow_controller(workflow_id) is not None


def test_worker_failure_reenters_runtime_through_typed_command() -> None:
    runtime, view, supervisor, _outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    workflow_id = view.snapshots[-1].session_id
    controller = workflow(view, workflow_id)
    invocation_id = controller.snapshot.active_invocation_id

    supervisor.error_handlers[invocation_id](RuntimeError("worker failed"))
    assert controller.snapshot.status != SessionStatus.FAILED

    runtime.drain_commands()
    assert controller.snapshot.status == SessionStatus.FAILED


def test_headless_submission_failure_releases_workflow_identity(monkeypatch) -> None:
    class FixedIdentity:
        hex = "headless-workflow"

    monkeypatch.setattr("ClipAI.app.runtime_workflows.uuid.uuid4", lambda: FixedIdentity())
    runtime, _view, _supervisor, _outputs, _listener = make_runtime(
        submit_error=RuntimeError("supervisor closed"),
    )

    runtime.enqueue(StartAction("a", "short", "speech"))
    runtime.enqueue(StartAction("a", "short", "speech"))
    runtime.drain_commands()

    runtime.enqueue(ActivateWorkflow("headless-workflow"))
    runtime.drain_commands()
    assert runtime._workflow_module.has_foreground_workflow() is False


def test_completed_pinned_session_survives_new_start() -> None:
    runtime, view, supervisor, _outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    session_id = view.snapshots[-1].session_id
    controller = workflow(view, session_id)
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
    controller = workflow(view, session_id)
    active_invocation = controller.snapshot.active_invocation_id
    controller._snapshot = controller.snapshot.evolve(content="clean result")
    runtime.enqueue(CopyResult(session_id, operation_id="copy-op"))
    runtime.enqueue(CloseSession(session_id))
    runtime.drain_commands()
    supervisor.work["copy-op"]()
    assert outputs.copied == ["clean result"]
    assert active_invocation in supervisor.cancelled
    assert view.workflow_controller(session_id) is None


def test_closed_popup_context_cannot_supply_a_new_action_input() -> None:
    runtime, view, supervisor, _outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    first_id = view.snapshots[-1].session_id
    view.context = ActiveWorkflowContext(first_id, "step-a", "stale popup result", None)

    runtime.enqueue(CloseSession(first_id))
    runtime.drain_commands()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()

    second_id = view.snapshots[-1].session_id
    second = workflow(view, second_id)
    supervisor.work[second.snapshot.active_invocation_id]()
    invocation = view.execute_action.invocations[-1]
    assert view.workflow_controller(first_id) is None
    assert invocation.input_target.kind == "external_text"


def test_copy_prefers_selected_command_text() -> None:
    runtime, view, _supervisor, outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    session_id = view.snapshots[-1].session_id
    controller = workflow(view, session_id)
    controller._snapshot = controller.snapshot.evolve(content="full result")
    runtime.enqueue(CopyResult(session_id, " selected ", "copy-op"))
    runtime.drain_commands()
    _supervisor.work["copy-op"]()
    assert outputs.copied == ["selected"]


def test_stop_releases_listener_supervisor_and_view() -> None:
    runtime, view, supervisor, _outputs, listener = make_runtime()
    runtime.start()
    runtime.stop()
    assert listener.stopped and supervisor.closed and view.stopped


def test_runtime_starts_and_stops_foreground_monitor() -> None:
    runtime, _view, _supervisor, _outputs, _listener = make_runtime()
    monitor = Monitor()
    runtime._foreground_monitor = monitor

    runtime.start()
    runtime.stop()

    assert monitor.started is True
    assert monitor.stopped is True


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
    controller = workflow(view, session_id)
    controller._snapshot = controller.snapshot.evolve(content="speak me")
    runtime.enqueue(ToggleSpeech(session_id))
    runtime.drain_commands()
    assert controller.snapshot.speaking is True
    operation_id = view.speech_coordinator.operation_for(session_id)
    work = supervisor.work[operation_id]
    work()
    assert outputs.spoken == ["speak me"]
    assert controller.snapshot.speaking is False


def test_global_speech_shortcut_stops_popup_speech_and_resets_speaker_state() -> None:
    runtime, view, supervisor, outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    session_id = view.snapshots[-1].session_id
    controller = workflow(view, session_id)
    controller._snapshot = controller.snapshot.evolve(content="speak me")
    runtime.enqueue(ToggleSpeech(session_id, operation_id="popup-speech"))
    runtime.drain_commands()
    assert controller.snapshot.speaking is True

    runtime.enqueue(ShortcutPressInvoked(ShortcutPressId(1), "speech", "short"))
    runtime.drain_commands()

    assert view.speech_coordinator.current_identity is None
    assert controller.snapshot.speaking is False
    assert outputs.stops == 1
    assert supervisor.cancelled == ["popup-speech"]


def test_late_completion_from_stopped_speech_cannot_clear_new_speaker_state() -> None:
    runtime, view, supervisor, _outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    session_id = view.snapshots[-1].session_id
    controller = workflow(view, session_id)
    controller._snapshot = controller.snapshot.evolve(content="speak me")
    runtime.enqueue(ToggleSpeech(session_id, operation_id="old-speech"))
    runtime.drain_commands()
    old_work = supervisor.work["old-speech"]

    runtime.enqueue(SpeakSelectionOrClipboard())
    runtime.enqueue(ToggleSpeech(session_id, operation_id="new-speech"))
    runtime.drain_commands()
    old_work()

    assert view.speech_coordinator.current_identity == ("new-speech", session_id)
    assert controller.snapshot.speaking is True


def test_speech_prefers_selected_command_text() -> None:
    runtime, view, supervisor, outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    session_id = view.snapshots[-1].session_id
    controller = workflow(view, session_id)
    controller._snapshot = controller.snapshot.evolve(content="full")
    runtime.enqueue(ToggleSpeech(session_id, "selected"))
    runtime.drain_commands()
    supervisor.work[view.speech_coordinator.operation_for(session_id)]()
    assert outputs.spoken == ["selected"]


def test_speech_reports_one_external_api_lifecycle() -> None:
    operations = OperationTracker()
    runtime, view, supervisor, _outputs, _listener = make_runtime(operation_tracker=operations)
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    session_id = view.snapshots[-1].session_id
    controller = workflow(view, session_id)
    controller._snapshot = controller.snapshot.evolve(content="speak")
    runtime.enqueue(ToggleSpeech(session_id))
    runtime.drain_commands()
    operation_id = view.speech_coordinator.operation_for(session_id)
    supervisor.work[operation_id]()
    assert operations.events == [("start", f"tts:{operation_id}", "tts"), ("success", f"tts:{operation_id}")]


def test_pinned_popup_stops_owned_speech_before_reusing_the_visible_action() -> None:
    runtime, view, _supervisor, outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    first_id = view.snapshots[-1].session_id
    first = workflow(view, first_id)
    first._snapshot = first.snapshot.evolve(status=SessionStatus.COMPLETED, content="first")
    runtime.enqueue(TogglePin(first_id))
    runtime.enqueue(ToggleSpeech(first_id, operation_id="speech-a"))
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()

    assert view.speech_coordinator.operation_for(first_id) is None
    assert outputs.stops == 1
    assert first.snapshot.pinned is True
    assert first.snapshot.active_invocation_id is not None
    assert view.attentions == []


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


def test_paste_and_archive_flow_through_typed_commands_without_claiming_delivery_confirmation() -> None:
    runtime, view, _supervisor, outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    session_id = view.snapshots[-1].session_id
    controller = workflow(view, session_id)
    controller._snapshot = controller.snapshot.evolve(content="use me")
    runtime.enqueue(ActivateWorkflow(session_id))
    runtime.drain_commands()
    assert runtime._user_control.focused_surface == ControlSurfaceRef(session_id, "workflow")
    runtime.enqueue(ArchiveResult(session_id, operation_id="archive-op"))
    runtime.drain_commands()
    _supervisor.work["archive-op"]()
    assert outputs.archived == ["use me"]
    runtime.enqueue(PasteResult(session_id, "selected", "paste-op"))
    runtime.drain_commands()
    assert view.workflow_controller(session_id) is not None
    _supervisor.work["paste-op"]()
    runtime.drain_commands()
    assert view.workflow_controller(session_id) is controller
    assert outputs.pasted == ["selected"]
    assert view.output_results[-1].state == "dispatched_unconfirmed"
    assert runtime._workflow_module.has_foreground_workflow() is False
    assert runtime._user_control.focused_surface is None


def test_pinned_unconfirmed_paste_preserves_workflow_and_foreground() -> None:
    runtime, view, supervisor, outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    session_id = view.snapshots[-1].session_id
    controller = workflow(view, session_id)
    controller._snapshot = controller.snapshot.evolve(content="use me")
    runtime.enqueue(TogglePin(session_id))
    runtime.drain_commands()

    runtime.enqueue(PasteResult(session_id, operation_id="paste-op"))
    runtime.drain_commands()
    supervisor.work["paste-op"]()
    runtime.drain_commands()

    assert view.workflow_controller(session_id) is controller
    assert controller.snapshot.pinned is True
    assert runtime._workflow_module.has_foreground_workflow() is True
    assert outputs.pasted == ["use me"]
    assert view.output_results[-1].state == "dispatched_unconfirmed"


@pytest.mark.parametrize(
    "outcome",
    (
        PasteOutcome("failed", "not_dispatched", "not_required"),
        PasteOutcome("cancelled", "not_dispatched", "restored"),
        PasteOutcome("cleanup_failed", "not_dispatched", "failed"),
    ),
)
def test_non_dispatched_paste_completion_does_not_release_foreground(outcome) -> None:
    runtime, view, _supervisor, _outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    workflow_id = view.snapshots[-1].session_id

    runtime.enqueue(PasteOperationCompleted("paste-op", workflow_id, outcome))
    runtime.drain_commands()

    assert runtime._workflow_module.has_foreground_workflow() is True


def test_dispatched_voice_paste_closes_the_unpinned_workflow_before_the_next_shortcut() -> None:
    runtime, _view, _supervisor, _outputs, _listener = make_runtime(include_voice_input=True)
    workflow_id = "voice-workflow"
    runtime._workflow_module.create_voice_workflow(
        workflow_id,
        PasteTarget("hwnd:10", 42, "Notepad", "Untitled", 1),
    )

    runtime.enqueue(PasteOperationCompleted(
        "paste-op",
        workflow_id,
        PasteOutcome("dispatched_unconfirmed", "dispatched_unconfirmed", "restored"),
    ))
    runtime.drain_commands()

    assert runtime._workflow_module.controller_for(workflow_id) is None
    assert runtime._workflow_module.has_foreground_workflow() is False


def test_completion_for_non_foreground_workflow_does_not_release_current_foreground() -> None:
    runtime, view, _supervisor, _outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    old_workflow_id = view.snapshots[-1].session_id
    runtime.enqueue(TogglePin(old_workflow_id))
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    current_workflow_id = view.snapshots[-1].session_id

    runtime.enqueue(PasteOperationCompleted(
        "old-paste",
        old_workflow_id,
        PasteOutcome("dispatched_unconfirmed", "dispatched_unconfirmed", "restored"),
    ))
    runtime.drain_commands()

    assert runtime._workflow_module.has_foreground_workflow() is True
    assert runtime._workflow_module._foreground_id == current_workflow_id


def test_overlapping_paste_on_the_single_popup_is_rejected_without_cancelling_active_dispatch() -> None:
    runtime, view, supervisor, _outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    workflow_id = view.snapshots[-1].session_id
    controller = workflow(view, workflow_id)
    controller._snapshot = controller.snapshot.evolve(content="first")

    runtime.enqueue(PasteResult(workflow_id, operation_id="old-paste"))
    runtime.enqueue(PasteResult(workflow_id, operation_id="new-paste"))
    runtime.drain_commands()

    assert view.output_results[-1].operation_id == "new-paste"
    assert view.output_results[-1].state == "failed"
    assert "new-paste" not in supervisor.work

    supervisor.work["old-paste"]()
    runtime.drain_commands()

    assert view.workflow_controller(workflow_id) is controller
    assert _outputs.pasted == ["first"]


def test_paste_captures_latest_target_when_operation_begins() -> None:
    runtime, view, supervisor, outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    session_id = view.snapshots[-1].session_id
    controller = workflow(view, session_id)
    controller._snapshot = controller.snapshot.evolve(content="use me")
    target_two = PasteTarget("hwnd:20", 84, "Writer", "Draft", 2)
    target_three = PasteTarget("hwnd:30", 126, "Mail", "Reply", 3)

    runtime.enqueue(ExternalForegroundChanged(target_two))
    runtime.enqueue(PasteResult(session_id, operation_id="paste-op"))
    runtime.drain_commands()
    runtime.enqueue(ExternalForegroundChanged(target_three))
    runtime.drain_commands()
    supervisor.work["paste-op"]()

    assert outputs.paste_targets == [target_two]
    assert view.paste_target_states[-1] == target_three


def test_targetless_voice_draft_uses_latest_target_when_paste_begins() -> None:
    runtime, view, supervisor, outputs, _listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    workflow_id = view.snapshots[-1].session_id
    controller = workflow(view, workflow_id)
    controller._snapshot = controller.snapshot.evolve(
        content="dictated text",
        voice_origin=VoiceOrigin(None, "dictated text"),
    )

    runtime.enqueue(PasteResult(workflow_id, operation_id="paste-op"))
    runtime.drain_commands()
    supervisor.work["paste-op"]()

    assert outputs.paste_targets == [
        PasteTarget("hwnd:10", 42, "Notepad", "Untitled", 1)
    ]


def test_paste_without_target_fails_without_scheduling_keyboard_output() -> None:
    runtime, view, supervisor, outputs, _listener = make_runtime()
    runtime._result_output_module._paste_targets = PasteTargetCoordinator(view)
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    session_id = view.snapshots[-1].session_id
    controller = workflow(view, session_id)
    controller._snapshot = controller.snapshot.evolve(content="use me")

    runtime.enqueue(PasteResult(session_id, operation_id="paste-op"))
    runtime.drain_commands()

    assert "paste-op" not in supervisor.work
    assert outputs.pasted == []
    assert view.output_results[-1].state == "failed"
    assert view.output_results[-1].reason == "no_target_observed"
    assert outputs.copied == ["use me"]
    assert "Ctrl+V" in view.output_results[-1].error.message


@pytest.mark.parametrize(
    ("outcome", "expects_copy"),
    (
        (
            PasteOutcome(
                "failed",
                "not_dispatched",
                "restored",
                "target changed",
                "target_changed",
            ),
            True,
        ),
        (PasteOutcome("cancelled", "not_dispatched", "restored"), True),
        (
            PasteOutcome(
                "dispatched_unconfirmed",
                "dispatched_unconfirmed",
                "restored",
            ),
            False,
        ),
        (
            PasteOutcome(
                "cleanup_failed",
                "dispatched_unconfirmed",
                "failed",
                reason="clipboard_unavailable",
            ),
            False,
        ),
    ),
)
def test_paste_terminal_state_controls_clipboard_fallback(outcome, expects_copy) -> None:
    runtime, view, _supervisor, outputs, _listener = make_runtime()
    workflow_id = "workflow-fallback"
    intent = OutputOperationIntent("paste-fallback", workflow_id, "paste", "canonical result")
    runtime._result_output_module._operations.begin(intent)
    bits_before = outputs.clipboard_bits

    runtime.enqueue(PasteOperationCompleted(intent.operation_id, workflow_id, outcome))
    runtime.drain_commands()

    if expects_copy:
        assert outputs.copied == ["canonical result"]
        assert outputs.clipboard_bits == b"canonical result"
        terminal = view.output_results[-1]
        message = terminal.error.message if terminal.error is not None else terminal.message
        assert "Ctrl+V" in message
    else:
        assert outputs.copied == []
        assert outputs.clipboard_bits == bits_before


def test_failed_paste_fallback_copy_failure_settles_with_clipboard_reason() -> None:
    runtime, view, _supervisor, outputs, _listener = make_runtime()
    outputs.copy_error = OSError("clipboard busy")
    intent = OutputOperationIntent("paste-copy-failed", "workflow", "paste", "result")
    runtime._result_output_module._operations.begin(intent)

    runtime.enqueue(PasteOperationCompleted(
        intent.operation_id,
        intent.workflow_id,
        PasteOutcome(
            "failed",
            "not_dispatched",
            "restored",
            "target changed",
            "target_changed",
        ),
    ))
    runtime.drain_commands()

    assert view.output_results[-1].state == "failed"
    assert view.output_results[-1].reason == "clipboard_unavailable"
    assert outputs.clipboard_bits == b"\x00\xfforiginal\x00"
