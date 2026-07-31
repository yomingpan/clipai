from __future__ import annotations

import asyncio
from dataclasses import replace

from ClipAI.core.models import ActionFeedbackContract, ActionInvocation, ActionVariant, FeedbackReason, GuidancePreferences, InputTarget, LLMCompleted, LLMRequest, LLMResult, OutputProfile, ReadinessIssue, ResolvedAction
from ClipAI.core.errors import ProviderResponseError
from ClipAI.core.state import CancellationToken, SessionSnapshot, SessionStatus
from ClipAI.providers.fake import FakeProvider
from ClipAI.services.execute_action import ActionExecutor
from ClipAI.services.input_resolver import InputResolver
from ClipAI.services.prompt_builder import PromptBuilder
from ClipAI.services.provider_binding import ProviderExecutionBinding
from ClipAI.services.result_processor import ResultProcessor
from ClipAI.services.output_profiles import OutputProfileCatalog
from ClipAI.services.workflow_controller import WorkflowController
from ClipAI.services.guidance_preferences import GuidancePreferencesCoordinator


class FakeClipboard:
    def __init__(self, text: str) -> None:
        self.text = text
        self.writes: list[str] = []

    def read_text(self) -> str:
        return self.text

    def read_image(self):
        return None

    def write_text(self, text: str) -> None:
        self.writes.append(text)


class FakeSelection:
    def __init__(self, text: str) -> None:
        self.text = text

    def read_text(self, cancellation=None) -> str:
        return self.text


class RecordingPresenter:
    def __init__(self) -> None:
        self.snapshots: list[SessionSnapshot] = []

    def render(self, snapshot: SessionSnapshot) -> None:
        self.snapshots.append(snapshot)


class RecordingOperation:
    def __init__(self, events: list[tuple[str, ...]], operation_id: str) -> None:
        self.events = events
        self.operation_id = operation_id

    def succeed(self) -> None:
        self.events.append(("success", self.operation_id))

    def fail(self) -> None:
        self.events.append(("error", self.operation_id))

    def cancel(self) -> None:
        self.events.append(("cancel", self.operation_id))


class RecordingOperations:
    def __init__(self) -> None:
        self.events: list[tuple[str, ...]] = []

    def start(self, operation_id: str, kind: str):
        self.events.append(("start", operation_id, kind))
        return RecordingOperation(self.events, operation_id)


def action() -> ResolvedAction:
    return ResolvedAction(
        id="english",
        name="English",
        system_prompt="Coach",
        prompt="Learn: {input}",
        press_type="short",
        input_mode="selection_or_clipboard",
        output_mode="popup",
        temperature=None,
    )


def workflow(clipboard: FakeClipboard, selection: FakeSelection, provider=None, operation_tracker=None, readiness_issues=(), guidance_preferences=None) -> ActionExecutor:
    return ActionExecutor(
        input_resolver=InputResolver(clipboard, selection),
        prompt_builder=PromptBuilder(),
        result_processor=ResultProcessor(),
        default_temperature=0.2,
        operation_tracker=operation_tracker,
        guidance_preferences=guidance_preferences,
    )


def binding(provider=None, readiness_issues=()) -> ProviderExecutionBinding:
    return ProviderExecutionBinding(provider or FakeProvider("result"), "fake", "model", readiness_issues)


def run_invocation(
    use_case: ActionExecutor,
    *,
    invocation_id: str = "i1",
    provider=None,
    readiness_issues=(),
    resolved_action: ResolvedAction | None = None,
) -> WorkflowController:
    presenter = RecordingPresenter()
    controller = WorkflowController(
        SessionSnapshot("w1", 0, SessionStatus.CREATED, "english", "English", "model"),
        presenter,
    )
    resolved = resolved_action or action()
    invocation = ActionInvocation(invocation_id, "english", resolved.press_type, InputTarget("external_text"), workflow_id="w1")
    controller.begin_invocation(invocation, resolved)
    asyncio.run(use_case.execute_invocation(
        resolved,
        invocation,
        controller,
        binding=binding(provider, readiness_issues),
    ))
    return controller


class GuidanceStore:
    def __init__(self) -> None:
        self.preferences = GuidancePreferences(True)

    def load(self):
        return self.preferences

    def save(self, preferences) -> None:
        self.preferences = preferences


def test_first_successful_feedback_recipe_projects_guidance_once() -> None:
    store = GuidanceStore()
    guidance = GuidancePreferencesCoordinator(store)
    resolved = replace(action(), feedback_contract=ActionFeedbackContract(
        "Translate",
        "Do not change intent",
        (FeedbackReason("other", "Other"),),
    ))
    executor = workflow(FakeClipboard("clipboard"), FakeSelection("selected"), guidance_preferences=guidance)

    first = run_invocation(executor, invocation_id="first", resolved_action=resolved)
    second = run_invocation(executor, invocation_id="second", resolved_action=resolved)
    long_resolved = replace(resolved, press_type="long", feedback_contract=replace(
        resolved.feedback_contract,
        ai_help_label="Improve English",
    ))
    long_first = run_invocation(executor, invocation_id="long-first", resolved_action=long_resolved)
    long_second = run_invocation(executor, invocation_id="long-second", resolved_action=long_resolved)

    assert first.snapshot.show_guidance_hint is True
    assert second.snapshot.show_guidance_hint is False
    assert long_first.snapshot.show_guidance_hint is True
    assert long_second.snapshot.show_guidance_hint is False


def test_execute_action_uses_selection_before_clipboard() -> None:
    session = run_invocation(workflow(FakeClipboard("clipboard"), FakeSelection("selected")))
    assert session.snapshot.status == SessionStatus.COMPLETED
    assert session.snapshot.original_input == "selected"
    assert session.snapshot.source_preview == "Selection: selected"
    assert session.snapshot.content == "result"


def test_execute_invocation_appends_successful_workflow_step() -> None:
    presenter = RecordingPresenter()
    controller = WorkflowController(
        SessionSnapshot("w1", 0, SessionStatus.CREATED, "english", "English", "model"),
        presenter,
    )
    invocation = ActionInvocation("i1", "english", "short", InputTarget("external_text"), workflow_id="w1")
    resolved = action()
    controller.begin_invocation(invocation, resolved)
    asyncio.run(workflow(FakeClipboard("clipboard"), FakeSelection("selected")).execute_invocation(
        resolved, invocation, controller, binding=binding()
    ))
    assert controller.snapshot.status == SessionStatus.COMPLETED
    assert controller.snapshot.content == "result"
    assert controller.snapshot.steps[0].input_text == "selected"
    assert controller.snapshot.steps[0].step_id == "i1"


def test_replaced_invocation_cancels_operation_without_late_success() -> None:
    presenter = RecordingPresenter()
    controller = WorkflowController(
        SessionSnapshot("w1", 0, SessionStatus.CREATED, "english", "English", "model"),
        presenter,
    )
    resolved = action()
    old = ActionInvocation("old", "english", "short", InputTarget("external_text"), workflow_id="w1")
    replacement = ActionInvocation("new", "english", "short", InputTarget("external_text"), workflow_id="w1")

    class ReplacingProvider:
        async def execute(self, request, cancellation, *, stream):
            controller.begin_invocation(replacement, resolved)
            yield LLMCompleted(LLMResult("late", "fake", request.model))

    operations = RecordingOperations()
    controller.begin_invocation(old, resolved)
    provider = ReplacingProvider()
    asyncio.run(workflow(
        FakeClipboard("clipboard"),
        FakeSelection("selected"),
        operation_tracker=operations,
    ).execute_invocation(resolved, old, controller, binding=binding(provider)))
    assert operations.events == [("start", "llm:old", "llm"), ("cancel", "llm:old")]
    assert controller.snapshot.active_invocation_id == "new"
    assert controller.snapshot.content == ""


def test_llm_reports_only_the_provider_call_lifecycle() -> None:
    operations = RecordingOperations()
    run_invocation(workflow(FakeClipboard("clipboard"), FakeSelection("selected"), operation_tracker=operations))
    assert operations.events == [("start", "llm:i1", "llm"), ("success", "llm:i1")]


def test_llm_reports_provider_error_without_false_success() -> None:
    class FailingProvider:
        async def execute(self, request, cancellation, *, stream):
            raise ProviderResponseError("provider failed")
            yield

    operations = RecordingOperations()
    provider = FailingProvider()
    session = run_invocation(workflow(
        FakeClipboard("clipboard"),
        FakeSelection("selected"),
        operation_tracker=operations,
    ), provider=provider)
    assert operations.events == [("start", "llm:i1", "llm"), ("error", "llm:i1")]
    assert session.snapshot.status == SessionStatus.FAILED


def test_missing_provider_key_fails_before_input_or_provider_call() -> None:
    class NeverProvider:
        async def execute(self, request, cancellation, *, stream):
            raise AssertionError("provider must not be called")
            yield

    issue = ReadinessIssue("provider.missing_api_key", "Set GEMINI_API_KEY and restart ClipAI.", "llm")
    provider = NeverProvider()
    session = run_invocation(workflow(
        FakeClipboard("clipboard"),
        FakeSelection("selected"),
    ), provider=provider, readiness_issues=(issue,))
    assert session.snapshot.status == SessionStatus.FAILED
    assert session.snapshot.error == issue.message


def test_empty_input_fails_without_calling_provider() -> None:
    class NeverProvider:
        async def execute(self, request, cancellation, *, stream):
            raise AssertionError("provider must not be called")
            yield

    session = run_invocation(workflow(FakeClipboard(""), FakeSelection("")), provider=NeverProvider())
    assert session.snapshot.status == SessionStatus.FAILED
    assert "No text found" in session.snapshot.error


def test_follow_up_keeps_previous_context() -> None:
    class RecordingProvider:
        def __init__(self) -> None:
            self.requests: list[LLMRequest] = []

        async def execute(self, request: LLMRequest, cancellation: CancellationToken, *, stream):
            self.requests.append(request)
            yield LLMCompleted(LLMResult("first" if len(self.requests) == 1 else "followed", "fake", request.model))

    provider = RecordingProvider()
    use_case = workflow(FakeClipboard("appetizer"), FakeSelection(""))
    session = run_invocation(use_case, provider=provider)
    parent = session.snapshot.steps[-1]
    follow = ActionInvocation(
        "i2",
        "english",
        "short",
        InputTarget("workflow_result"),
        workflow_id="w1",
        parent_step_id=parent.step_id,
    )
    session.begin_invocation(follow, action())
    asyncio.run(use_case.execute_follow_up_invocation(
        action(),
        "More examples?",
        follow,
        session,
        original_input=session.snapshot.original_input,
        previous_result=parent.result_text,
        binding=binding(provider),
    ))
    assert session.snapshot.content == "followed"
    assert [message.role for message in provider.requests[1].messages] == ["system", "user", "assistant", "user"]
    assert provider.requests[1].messages[-1].content == "More examples?"


def test_prompt_builder_includes_app_and_action_system_prompts() -> None:
    request = PromptBuilder("App policy").build(
        action(),
        "input",
        model="model",
        default_temperature=0.2,
    )
    assert request.messages[0].content == "App policy\n\nCoach"


def test_prompt_builder_adds_output_profile_instruction_once() -> None:
    profile = OutputProfile("compact", "Return exactly four lines.", ("Synonym:",))
    catalog = OutputProfileCatalog([profile])
    profiled = ResolvedAction(**{**action().__dict__, "output_profile": "compact"})
    request = PromptBuilder("App policy", catalog).build(profiled, "input", model="model", default_temperature=0.2)
    assert request.messages[0].content.count("Return exactly four lines.") == 1


def test_result_processor_warns_but_preserves_text_when_profile_marker_is_missing(caplog) -> None:
    profile = OutputProfile("compact", "", ("Synonym:",))
    processor = ResultProcessor(OutputProfileCatalog([profile]))
    result = processor.process("Useful readable result", "compact")
    assert result.text == "Useful readable result"
    assert "missing markers: Synonym:" in caplog.text


def test_result_processor_warns_for_too_many_sections_and_nested_lists(caplog) -> None:
    text = "\n".join([f"# Section {index}" for index in range(5)]) + "\n  - nested"
    processed = ResultProcessor().process(text)
    assert processed.text == text
    assert processed.document is not None
    assert "exceeds four top-level sections" in caplog.text
    assert "unsupported nested list structure" in caplog.text
