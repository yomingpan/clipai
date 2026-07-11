from __future__ import annotations

from ClipAI.core.models import ActionVariant, LLMRequest, LLMResult, OutputProfile, ReadinessIssue, ResolvedAction
from ClipAI.core.errors import ProviderResponseError
from ClipAI.core.state import CancellationToken, SessionSnapshot, SessionStatus
from ClipAI.providers.fake import FakeProvider
from ClipAI.services.execute_action import ExecuteAction
from ClipAI.services.input_resolver import InputResolver
from ClipAI.services.prompt_builder import PromptBuilder
from ClipAI.services.result_processor import ResultProcessor
from ClipAI.services.output_profiles import OutputProfileCatalog
from ClipAI.services.session_controller import SessionController


class FakeClipboard:
    def __init__(self, text: str) -> None:
        self.text = text
        self.writes: list[str] = []

    def read_text(self) -> str:
        return self.text

    def write_text(self, text: str) -> None:
        self.writes.append(text)


class FakeSelection:
    def __init__(self, text: str) -> None:
        self.text = text

    def read_text(self) -> str:
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


def controller(presenter: RecordingPresenter | None = None) -> SessionController:
    return SessionController(
        SessionSnapshot("s1", 0, SessionStatus.CREATED, "english", "English", "model"),
        presenter or RecordingPresenter(),
    )


def workflow(clipboard: FakeClipboard, selection: FakeSelection, provider=None, operation_tracker=None, readiness_issues=()) -> ExecuteAction:
    return ExecuteAction(
        input_resolver=InputResolver(clipboard, selection),
        provider=provider or FakeProvider("result"),
        prompt_builder=PromptBuilder(),
        result_processor=ResultProcessor(),
        model="model",
        default_temperature=0.2,
        provider_name="fake",
        operation_tracker=operation_tracker,
        readiness_issues=readiness_issues,
    )


def test_execute_action_uses_selection_before_clipboard() -> None:
    session = controller()
    workflow(FakeClipboard("clipboard"), FakeSelection("selected")).execute(action(), session)
    assert session.snapshot.status == SessionStatus.COMPLETED
    assert session.snapshot.original_input == "selected"
    assert session.snapshot.source_preview == "Selection: selected"
    assert session.snapshot.content == "result"


def test_llm_reports_only_the_provider_call_lifecycle() -> None:
    operations = RecordingOperations()
    session = controller()
    workflow(FakeClipboard("clipboard"), FakeSelection("selected"), operation_tracker=operations).execute(action(), session)
    assert operations.events == [("start", "llm:s1", "llm"), ("success", "llm:s1")]


def test_llm_reports_provider_error_without_false_success() -> None:
    class FailingProvider:
        def complete(self, request, cancellation):
            raise ProviderResponseError("provider failed")

    operations = RecordingOperations()
    session = controller()
    workflow(
        FakeClipboard("clipboard"),
        FakeSelection("selected"),
        provider=FailingProvider(),
        operation_tracker=operations,
    ).execute(action(), session)
    assert operations.events == [("start", "llm:s1", "llm"), ("error", "llm:s1")]
    assert session.snapshot.status == SessionStatus.FAILED


def test_missing_provider_key_fails_before_input_or_provider_call() -> None:
    class NeverProvider:
        def complete(self, request, cancellation):
            raise AssertionError("provider must not be called")

    issue = ReadinessIssue("provider.missing_api_key", "Set GEMINI_API_KEY and restart ClipAI.", "llm")
    session = controller()
    workflow(
        FakeClipboard("clipboard"),
        FakeSelection("selected"),
        provider=NeverProvider(),
        readiness_issues=(issue,),
    ).execute(action(), session)
    assert session.snapshot.status == SessionStatus.FAILED
    assert session.snapshot.error == issue.message


def test_empty_input_fails_without_calling_provider() -> None:
    class NeverProvider:
        def complete(self, request, cancellation):
            raise AssertionError("provider must not be called")

    session = controller()
    workflow(FakeClipboard(""), FakeSelection(""), NeverProvider()).execute(action(), session)
    assert session.snapshot.status == SessionStatus.FAILED
    assert "No text found" in session.snapshot.error


def test_cancelled_session_ignores_late_result() -> None:
    presenter = RecordingPresenter()
    session = controller(presenter)
    session.transition(SessionStatus.READING_INPUT)
    session.transition(SessionStatus.PREPARING_REQUEST)
    session.transition(SessionStatus.REQUESTING_PROVIDER)
    session.cancel()
    revision = session.snapshot.revision
    assert session.transition(SessionStatus.PROCESSING_RESULT, content="late") is None
    assert session.snapshot.revision == revision
    assert session.snapshot.status == SessionStatus.CANCELLED


def test_follow_up_keeps_previous_context() -> None:
    class RecordingProvider:
        def __init__(self) -> None:
            self.requests: list[LLMRequest] = []

        def complete(self, request: LLMRequest, cancellation: CancellationToken) -> LLMResult:
            self.requests.append(request)
            return LLMResult("first" if len(self.requests) == 1 else "followed", "fake", request.model)

    provider = RecordingProvider()
    session = controller()
    use_case = workflow(FakeClipboard("appetizer"), FakeSelection(""), provider)
    use_case.execute(action(), session)
    use_case.execute_follow_up(action(), "More examples?", session)
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
