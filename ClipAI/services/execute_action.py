from __future__ import annotations

from ClipAI.core.errors import CancelledError, ClipAIError
from ClipAI.core.models import LLMRequest, LLMResult, ResolvedAction
from ClipAI.core.ports import LLMProvider, StatusIndicator
from ClipAI.core.state import SessionStatus
from ClipAI.services.input_resolver import InputResolver
from ClipAI.services.prompt_builder import PromptBuilder
from ClipAI.services.result_processor import ResultProcessor
from ClipAI.services.session_controller import SessionController


class ExecuteAction:
    def __init__(
        self,
        *,
        input_resolver: InputResolver,
        provider: LLMProvider,
        prompt_builder: PromptBuilder,
        result_processor: ResultProcessor,
        model: str,
        default_temperature: float,
        provider_name: str,
        available_actions: tuple[str, ...] = ("copy", "follow_up"),
        status_indicator: StatusIndicator | None = None,
    ) -> None:
        self._input_resolver = input_resolver
        self._provider = provider
        self._prompt_builder = prompt_builder
        self._result_processor = result_processor
        self._model = model
        self._default_temperature = default_temperature
        self._provider_name = provider_name
        self._available_actions = available_actions
        self._status_indicator = status_indicator

    def execute(self, action: ResolvedAction, session: SessionController) -> None:
        try:
            if session.transition(SessionStatus.READING_INPUT, status_text="Reading input...") is None:
                return
            document = self._input_resolver.resolve(action.input_mode)
            if session.transition(
                SessionStatus.PREPARING_REQUEST,
                status_text=f"Preparing {action.name}...",
                source_preview=_source_preview(document.source, document.text),
                original_input=document.text,
            ) is None:
                return
            request = self._prompt_builder.build(
                action,
                document.text,
                model=self._model,
                default_temperature=self._default_temperature,
            )
            if session.transition(
                SessionStatus.REQUESTING_PROVIDER,
                status_text=f"Asking {self._provider_name}...",
            ) is None:
                return
            result = self._complete_provider(request, session)
            if session.transition(SessionStatus.PROCESSING_RESULT, status_text="Rendering result...") is None:
                return
            processed = self._result_processor.process(result.text, action.output_profile)
            session.transition(
                SessionStatus.COMPLETED,
                status_text="Completed",
                content=processed.text,
                available_actions=self._available_actions,
            )
        except CancelledError:
            session.cancel()
        except ClipAIError as exc:
            session.fail(str(exc))

    def execute_follow_up(self, action: ResolvedAction, question: str, session: SessionController) -> None:
        previous = session.snapshot
        if previous.status != SessionStatus.COMPLETED or not question.strip():
            return
        try:
            if session.transition(SessionStatus.PREPARING_REQUEST, status_text="Preparing follow-up...") is None:
                return
            request = self._prompt_builder.build_follow_up(
                action,
                original_input=previous.original_input,
                previous_result=previous.content,
                question=question.strip(),
                model=self._model,
                default_temperature=self._default_temperature,
            )
            if session.transition(SessionStatus.REQUESTING_PROVIDER, status_text=f"Asking {self._provider_name}...") is None:
                return
            result = self._complete_provider(request, session)
            if session.transition(SessionStatus.PROCESSING_RESULT, status_text="Rendering result...") is None:
                return
            processed = self._result_processor.process(result.text, action.output_profile)
            session.transition(
                SessionStatus.COMPLETED,
                status_text="Completed",
                content=processed.text,
                available_actions=self._available_actions,
            )
        except CancelledError:
            session.cancel()
        except ClipAIError as exc:
            session.fail(str(exc))

    def _complete_provider(self, request: LLMRequest, session: SessionController) -> LLMResult:
        if self._status_indicator is not None:
            self._status_indicator.set_status("processing")
        try:
            result = self._provider.complete(request, session.cancellation)
        except CancelledError:
            if self._status_indicator is not None:
                self._status_indicator.set_status("idle")
            raise
        except BaseException:
            if self._status_indicator is not None:
                self._status_indicator.set_status("error")
            raise
        if self._status_indicator is not None:
            self._status_indicator.set_status("success")
        return result


def _source_preview(source: str, text: str, limit: int = 90) -> str:
    compact = " ".join(text.split())
    if len(compact) > limit:
        compact = f"{compact[: limit - 1]}..."
    return f"{source.title()}: {compact}"
