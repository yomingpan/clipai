from __future__ import annotations

from ClipAI.app.task_supervisor import TaskSupervisor
from ClipAI.core.state import CancellationToken
from ClipAI.services.speech_coordinator import SpeechCoordinator


class SupervisedSpeechResultSink:
    """Moves generated-result speech off the provider asyncio loop."""

    def __init__(self, coordinator: SpeechCoordinator, supervisor: TaskSupervisor) -> None:
        self._coordinator = coordinator
        self._supervisor = supervisor

    async def speak_result(
        self,
        text: str,
        workflow_id: str,
        cancellation: CancellationToken,
    ) -> None:
        job = self._coordinator.create_result_job(
            workflow_id=workflow_id,
            text=text,
            cancellation=cancellation,
        )
        await self._supervisor.run(
            f"speech:{job.operation_id}",
            job.run,
            task_class="media",
            cancellation_hook=lambda: self._coordinator.cancel_operation(job.operation_id),
        )
