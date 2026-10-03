"""Non-Workflow dictation refinement and paste dispatch."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from ClipAI.app.provider_execution import ProviderExecutionModule
from ClipAI.core.errors import CancelledError, InlineRefinementFailureReason, ProviderTimeoutError, ProviderUnavailableError
from ClipAI.core.models import PasteTarget, ResolvedAction
from ClipAI.core.state import CancellationToken
from ClipAI.services.execute_action import ActionExecutor
from ClipAI.services.provider_binding import ProviderExecutionBinding


logger = logging.getLogger("clipai.inline_dictation")
INLINE_REFINEMENT_TIMEOUT_SECONDS = 75.0


class InlineDictationCoordinator:
    def __init__(
        self,
        *,
        provider_execution: ProviderExecutionModule,
        executor: ActionExecutor | None,
        refine_action: ResolvedAction | None,
        binding: Callable[[], ProviderExecutionBinding | None],
        paste: Callable[[str, PasteTarget, str, str], None],
        on_refine_settled: Callable[[str, str, str, bool, InlineRefinementFailureReason | None], None],
    ) -> None:
        self._provider_execution = provider_execution
        self._executor = executor
        self._refine_action = refine_action
        self._binding = binding
        self._paste = paste
        self._on_refine_settled = on_refine_settled

    def submit(self, text: str, target: PasteTarget, *, refine: bool = False, interaction_id: str = "", operation_id: str = "") -> bool:
        if not operation_id:
            if refine:
                self._on_refine_settled(interaction_id, operation_id, "", True, "failed")
            return False
        if not text.strip():
            if refine:
                self._on_refine_settled(interaction_id, operation_id, "", True, "failed")
            return False
        action, executor = self._refine_action, self._executor
        try:
            binding = self._binding() if refine and action is not None and executor is not None else None
        except BaseException as error:
            logger.warning("Dictation refinement binding failed: %s", type(error).__name__)
            self._on_refine_settled(interaction_id, operation_id, "", True, "unavailable")
            return False
        if not refine or action is None or executor is None or binding is None:
            if refine:
                self._on_refine_settled(interaction_id, operation_id, "", True, "unavailable")
            else:
                self._paste(text, target, interaction_id, operation_id)
            return False
        cancellation = CancellationToken()

        def refine_settled(result: str) -> None:
            failed = not bool(result.strip())
            self._on_refine_settled(interaction_id, operation_id, result, failed, "failed" if failed else None)

        def fallback(error: BaseException | None = None) -> None:
            if error is not None:
                logger.warning("Dictation refinement failed: %s", type(error).__name__)
            reason: InlineRefinementFailureReason
            if isinstance(error, (asyncio.TimeoutError, TimeoutError, ProviderTimeoutError)):
                reason = "timed_out"
            elif isinstance(error, ProviderUnavailableError):
                reason = "unavailable"
            elif isinstance(error, CancelledError):
                reason = "cancelled"
            else:
                reason = "failed"
            self._on_refine_settled(interaction_id, operation_id, "", True, reason)

        try:
            self._provider_execution.start(
                operation_id,
                lambda: executor.refine_text(action, text, binding=binding, cancellation=cancellation),
                refine_settled,
                fallback,
                lambda: fallback(CancelledError("dictation refinement was cancelled")),
                timeout_seconds=INLINE_REFINEMENT_TIMEOUT_SECONDS,
            )
        except BaseException as error:
            fallback(error)
            return False
        return True

    def cancel(self, operation_id: str) -> bool:
        return self._provider_execution.cancel(operation_id)
