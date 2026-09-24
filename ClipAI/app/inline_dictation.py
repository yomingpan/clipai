"""Non-Workflow dictation refinement and paste dispatch."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable

from ClipAI.app.provider_execution import ProviderExecutionModule
from ClipAI.core.models import PasteTarget, ResolvedAction
from ClipAI.core.state import CancellationToken
from ClipAI.services.execute_action import ActionExecutor
from ClipAI.services.provider_binding import ProviderExecutionBinding


logger = logging.getLogger("clipai.inline_dictation")


class InlineDictationCoordinator:
    def __init__(
        self,
        *,
        provider_execution: ProviderExecutionModule,
        executor: ActionExecutor | None,
        refine_action: ResolvedAction | None,
        binding: Callable[[], ProviderExecutionBinding | None],
        paste: Callable[[str, PasteTarget], None],
        on_refine_settled: Callable[[str], None],
    ) -> None:
        self._provider_execution = provider_execution
        self._executor = executor
        self._refine_action = refine_action
        self._binding = binding
        self._paste = paste
        self._on_refine_settled = on_refine_settled

    def submit(self, text: str, target: PasteTarget, *, refine: bool = False, workflow_id: str = "") -> None:
        if not text.strip():
            if refine:
                self._on_refine_settled(workflow_id)
            return
        action, executor = self._refine_action, self._executor
        binding = self._binding() if refine and action is not None and executor is not None else None
        if not refine or action is None or executor is None or binding is None:
            self._paste(text, target)
            if refine:
                self._on_refine_settled(workflow_id)
            return
        cancellation = CancellationToken()

        def paste_settled(result: str) -> None:
            try:
                self._paste(result or text, target)
            finally:
                self._on_refine_settled(workflow_id)

        def fallback(error: BaseException | None = None) -> None:
            if error is not None:
                logger.warning("Dictation refinement failed: %s", type(error).__name__)
            paste_settled(text)

        try:
            self._provider_execution.start(
                f"inline-refine-{uuid.uuid4().hex}",
                lambda: executor.refine_text(action, text, binding=binding, cancellation=cancellation),
                paste_settled,
                fallback,
                lambda: fallback(),
            )
        except BaseException as error:
            fallback(error)
