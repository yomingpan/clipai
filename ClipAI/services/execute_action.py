from __future__ import annotations

from ClipAI.core.errors import CancelledError, ClipAIError
from ClipAI.core.models import ActionInvocation, InputDocument, LLMRequest, LLMResult, ResolvedAction
from ClipAI.core.ports import OperationHandle, OperationTracker
from ClipAI.core.state import SessionStatus
from ClipAI.services.input_resolver import InputResolver
from ClipAI.services.prompt_builder import PromptBuilder
from ClipAI.services.provider_binding import ProviderExecutionBinding
from ClipAI.services.result_processor import ResultProcessor
from ClipAI.services.result_router import ResultRouter
from ClipAI.services.workflow_controller import WorkflowController


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
    ) -> None:
        self._input_resolver = input_resolver
        self._prompt_builder = prompt_builder
        self._result_processor = result_processor
        self._default_temperature = default_temperature
        self._available_actions = available_actions
        self._operation_tracker = operation_tracker
        self._result_router = result_router or ResultRouter()

    def execute_invocation(
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
            document = invocation.input_target.document or self._input_resolver.resolve(action.input_mode)
            if workflow.update(
                invocation.invocation_id,
                SessionStatus.PREPARING_REQUEST,
                status_text=f"Preparing {action.name}...",
                input_source=document.source,
            ) is None:
                return
            request = self._prompt_builder.build(
                action,
                document.text,
                model=binding.model,
                default_temperature=self._default_temperature,
                image=document.image,
            )
            if workflow.update(
                invocation.invocation_id,
                SessionStatus.REQUESTING_PROVIDER,
                status_text=f"Asking {binding.provider_id}...",
            ) is None:
                return
            result = self._complete_provider_for_invocation(request, invocation.invocation_id, token, binding)
            if workflow.update(
                invocation.invocation_id,
                SessionStatus.PROCESSING_RESULT,
                status_text="Rendering result...",
            ) is None:
                return
            processed = self._result_processor.process(result.text, action.output_profile)
            self._result_router.route(
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
            workflow.fail(invocation.invocation_id, str(exc))

    def execute_follow_up_invocation(
        self,
        action: ResolvedAction,
        question: str,
        invocation: ActionInvocation,
        workflow: WorkflowController,
        *,
        original_input: str,
        previous_result: str,
        binding: ProviderExecutionBinding,
    ) -> None:
        token = workflow.cancellation
        try:
            if self._fail_workflow_if_not_ready(workflow, invocation.invocation_id, binding):
                return
            request = self._prompt_builder.build_follow_up(
                action,
                original_input=original_input,
                previous_result=previous_result,
                question=question,
                model=binding.model,
                default_temperature=self._default_temperature,
            )
            if workflow.update(
                invocation.invocation_id,
                SessionStatus.REQUESTING_PROVIDER,
                status_text=f"Asking {binding.provider_id}...",
            ) is None:
                return
            result = self._complete_provider_for_invocation(request, invocation.invocation_id, token, binding)
            if workflow.update(
                invocation.invocation_id,
                SessionStatus.PROCESSING_RESULT,
                status_text="Rendering result...",
            ) is None:
                return
            processed = self._result_processor.process(result.text, action.output_profile)
            document = InputDocument(question, "workflow_result", workflow.snapshot.session_id, invocation.parent_step_id)
            self._result_router.route(
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
                ),
            )
        except CancelledError:
            return
        except ClipAIError as exc:
            workflow.fail(invocation.invocation_id, str(exc))

    def _complete_provider_for_invocation(
        self,
        request: LLMRequest,
        invocation_id: str,
        cancellation,
        binding: ProviderExecutionBinding,
    ) -> LLMResult:
        operation: OperationHandle | None = None
        if self._operation_tracker is not None:
            operation = self._operation_tracker.start(f"llm:{invocation_id}", "llm")
        try:
            result = binding.provider.complete(request, cancellation)
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
