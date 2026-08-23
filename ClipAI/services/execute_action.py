from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import TypeVar

from ClipAI.core.errors import CancelledError, ClipAIError, ProviderUnavailableError
from ClipAI.core.models import ActionInvocation, LLMCompleted, LLMProviderEvent, LLMRequest, LLMResult, LLMTextDelta, ResolvedAction
from ClipAI.core.ports import OperationHandle, OperationTracker
from ClipAI.core.state import SessionStatus
from ClipAI.services.input_resolver import InputResolver
from ClipAI.services.follow_up_continuation import FollowUpContinuation
from ClipAI.services.prompt_builder import PromptBuilder
from ClipAI.services.provider_binding import ProviderExecutionBinding
from ClipAI.services.result_processor import ResultProcessor
from ClipAI.services.result_router import ResultRouter
from ClipAI.services.workflow_controller import WorkflowController
from ClipAI.services.user_preferences import UserPreferencesCoordinator


class ActionExecutor:
    def __init__(
        self,
        *,
        input_resolver: InputResolver,
        prompt_builder: PromptBuilder,
        result_processor: ResultProcessor,
        default_temperature: float,
        available_actions: tuple[str, ...] = ("copy", "follow_up"),
        operation_tracker: OperationTracker | None = None,
        result_router: ResultRouter | None = None,
        guidance_preferences: UserPreferencesCoordinator | None = None,
        blocking_runner: Callable[[str, Callable[[], object]], Awaitable[object]] | None = None,
    ) -> None:
        self._input_resolver = input_resolver
        self._prompt_builder = prompt_builder
        self._result_processor = result_processor
        self._default_temperature = default_temperature
        self._available_actions = available_actions
        self._operation_tracker = operation_tracker
        self._result_router = result_router or ResultRouter()
        self._guidance_preferences = guidance_preferences
        self._blocking_runner = blocking_runner

    async def execute_invocation(
        self,
        action: ResolvedAction,
        invocation: ActionInvocation,
        workflow: WorkflowController,
        *,
        binding: ProviderExecutionBinding,
    ) -> None:
        token = workflow.cancellation
        try:
            if self._fail_workflow_if_not_ready(workflow, invocation.invocation_id, binding):
                return
            document = invocation.input_target.document or await self._run_blocking(
                f"input:{invocation.invocation_id}",
                lambda: self._input_resolver.resolve(action.input_mode, token),
            )
            if workflow.update(
                invocation.invocation_id,
                SessionStatus.PREPARING_REQUEST,
                status_text=f"Preparing {action.name}...",
                input_source=document.source,
            ) is None:
                return
            request = await self._run_blocking(
                f"prompt:{invocation.invocation_id}",
                lambda: self._prompt_builder.build(
                    action,
                    document.text,
                    model=binding.model,
                    default_temperature=self._default_temperature,
                    image=document.image,
                ),
            )
            if workflow.update(
                invocation.invocation_id,
                SessionStatus.REQUESTING_PROVIDER,
                status_text=f"Asking {binding.provider_id}...",
            ) is None:
                return
            result = await self._complete_provider_for_invocation(request, invocation.invocation_id, token, binding, action.stream, workflow)
            if workflow.update(
                invocation.invocation_id,
                SessionStatus.PROCESSING_RESULT,
                status_text="Rendering result...",
            ) is None:
                return
            processed = await self._run_blocking(
                f"result:{invocation.invocation_id}",
                lambda: self._result_processor.process(result.text, action.output_profile),
            )
            show_guidance_hint = self._consume_guidance_hint(action, invocation)
            await self._result_router.route(
                invocation.result_route,
                processed,
                workflow_id=invocation.workflow_id or invocation.invocation_id,
                cancellation=token,
                popup_sink=lambda routed: workflow.complete(
                    invocation,
                    action,
                    document,
                    routed.text,
                    self._available_actions,
                    routed.document,
                    provider=result.provider,
                    model=result.model,
                    show_guidance_hint=show_guidance_hint,
                ),
            )
            if invocation.result_route == "speech":
                workflow.complete(
                    invocation,
                    action,
                    document,
                    processed.text,
                    (),
                    processed.document,
                    provider=result.provider,
                    model=result.model,
                )
        except CancelledError:
            return
        except ClipAIError as exc:
            workflow.fail(invocation.invocation_id, _provider_error_message(exc, binding.provider_id))

    async def execute_follow_up_invocation(
        self,
        continuation: FollowUpContinuation,
        invocation: ActionInvocation,
        workflow: WorkflowController,
        *,
        binding: ProviderExecutionBinding,
    ) -> None:
        action = continuation.action
        token = workflow.cancellation
        try:
            if self._fail_workflow_if_not_ready(workflow, invocation.invocation_id, binding):
                return
            document = continuation.input_document(workflow.snapshot.session_id)
            if workflow.update(
                invocation.invocation_id,
                SessionStatus.PREPARING_REQUEST,
                status_text=f"Preparing {action.name}...",
                input_source=document.source,
            ) is None:
                return
            request = await self._run_blocking(
                f"prompt:{invocation.invocation_id}",
                lambda: self._prompt_builder.build_follow_up(
                    continuation,
                    model=binding.model,
                    default_temperature=self._default_temperature,
                ),
            )
            if workflow.update(
                invocation.invocation_id,
                SessionStatus.REQUESTING_PROVIDER,
                status_text=f"Asking {binding.provider_id}...",
            ) is None:
                return
            result = await self._complete_provider_for_invocation(request, invocation.invocation_id, token, binding, action.stream, workflow)
            if workflow.update(
                invocation.invocation_id,
                SessionStatus.PROCESSING_RESULT,
                status_text="Rendering result...",
            ) is None:
                return
            processed = await self._run_blocking(
                f"result:{invocation.invocation_id}",
                lambda: self._result_processor.process(result.text, action.output_profile),
            )
            show_guidance_hint = self._consume_guidance_hint(action, invocation)
            await self._result_router.route(
                invocation.result_route,
                processed,
                workflow_id=invocation.workflow_id or invocation.invocation_id,
                cancellation=token,
                popup_sink=lambda routed: workflow.complete(
                    invocation,
                    action,
                    document,
                    routed.text,
                    self._available_actions,
                    routed.document,
                    provider=result.provider,
                    model=result.model,
                    show_guidance_hint=show_guidance_hint,
                ),
            )
        except CancelledError:
            return
        except ClipAIError as exc:
            workflow.fail(invocation.invocation_id, _provider_error_message(exc, binding.provider_id))

    def _consume_guidance_hint(self, action: ResolvedAction, invocation: ActionInvocation) -> bool:
        return bool(
            invocation.result_route == "popup"
            and action.feedback_contract is not None
            and self._guidance_preferences is not None
            and self._guidance_preferences.consume_first_use_hint(f"{action.id}:{action.press_type}")
        )

    async def _run_blocking(self, task_id: str, work: Callable[[], object]):
        if self._blocking_runner is None:
            return await asyncio.to_thread(work)
        return await self._blocking_runner(task_id, work)

    async def _complete_provider_for_invocation(
        self,
        request: LLMRequest,
        invocation_id: str,
        cancellation,
        binding: ProviderExecutionBinding,
        stream: bool,
        workflow: WorkflowController,
    ) -> LLMResult:
        operation: OperationHandle | None = None
        if self._operation_tracker is not None:
            operation = self._operation_tracker.start(f"llm:{invocation_id}", "llm")
        try:
            result: LLMResult | None = None
            events = binding.provider.execute(request, cancellation, stream=stream)
            async for event in coalesce_provider_events(events):
                if isinstance(event, LLMTextDelta):
                    if workflow.append_provider_text(invocation_id, event.text) is None:
                        raise CancelledError("action invocation was replaced")
                elif isinstance(event, LLMCompleted):
                    result = event.result
            if result is None:
                raise ClipAIError("AI provider did not return a terminal result")
        except asyncio.CancelledError:
            if operation is not None:
                operation.cancel()
            raise
        except CancelledError:
            if operation is not None:
                operation.cancel()
            raise
        except BaseException:
            if operation is not None:
                operation.fail()
            raise
        if cancellation.is_cancelled:
            if operation is not None:
                operation.cancel()
            raise CancelledError("action invocation was replaced")
        assert result is not None
        if operation is not None:
            operation.succeed()
        return result

    def _fail_workflow_if_not_ready(
        self,
        workflow: WorkflowController,
        invocation_id: str,
        binding: ProviderExecutionBinding,
    ) -> bool:
        issue = next((item for item in binding.readiness_issues if item.feature == "llm"), None)
        if issue is None:
            return False
        workflow.fail(invocation_id, issue.message)
        return True


def _provider_error_message(error: ClipAIError, provider_id: str) -> str:
    if isinstance(error, ProviderUnavailableError) and provider_id == "gateway":
        return "Custom provider is unavailable. Start it, then try again."
    return str(error)


async def coalesce_provider_events(
    events: AsyncIterator[LLMProviderEvent],
    *,
    interval_seconds: float = 0.04,
) -> AsyncIterator[LLMProviderEvent]:
    """Bound partial projection frequency while flushing terminal events immediately."""

    iterator = events.__aiter__()
    pending: asyncio.Task[LLMProviderEvent] | None = asyncio.create_task(anext(iterator))
    buffered: list[str] = []
    loop = asyncio.get_running_loop()
    deadline = 0.0
    try:
        while pending is not None:
            timeout = max(0.0, deadline - loop.time()) if buffered else None
            done, _ = await asyncio.wait((pending,), timeout=timeout)
            if not done:
                yield LLMTextDelta("".join(buffered))
                buffered.clear()
                continue
            try:
                event = pending.result()
            except StopAsyncIteration:
                pending = None
                break
            pending = asyncio.create_task(anext(iterator))
            if isinstance(event, LLMTextDelta):
                if not buffered:
                    deadline = loop.time() + interval_seconds
                buffered.append(event.text)
                continue
            if buffered:
                yield LLMTextDelta("".join(buffered))
                buffered.clear()
            yield event
    finally:
        if pending is not None and not pending.done():
            pending.cancel()
    if buffered:
        yield LLMTextDelta("".join(buffered))
