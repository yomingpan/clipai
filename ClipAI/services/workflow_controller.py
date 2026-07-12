from __future__ import annotations

import threading

from ClipAI.core.models import ActionInvocation, InputDocument, PresentationDocument, ResolvedAction, WorkflowStep
from ClipAI.core.ports import ResultPresenter
from ClipAI.core.state import CancellationToken, SessionSnapshot, SessionStatus


class WorkflowController:
    """Single owner for one popup workflow and its linear successful-step history."""

    def __init__(self, initial: SessionSnapshot, presenter: ResultPresenter) -> None:
        self._snapshot = initial
        self._presenter = presenter
        self._lock = threading.RLock()
        self._active_token = CancellationToken()
        self._presenter.render(initial)

    @property
    def snapshot(self) -> SessionSnapshot:
        with self._lock:
            return self._snapshot

    @property
    def cancellation(self) -> CancellationToken:
        with self._lock:
            return self._active_token

    def begin_invocation(self, invocation: ActionInvocation, action: ResolvedAction) -> CancellationToken:
        with self._lock:
            self._active_token.cancel()
            self._active_token = CancellationToken()
            status = SessionStatus.READING_INPUT if invocation.input_target.document is None else SessionStatus.PREPARING_REQUEST
            status_text = "Reading input..." if status == SessionStatus.READING_INPUT else f"Preparing {action.name}..."
            self._snapshot = self._snapshot.evolve(
                status=status,
                action_id=action.id,
                title=action.name,
                status_text=status_text,
                error="",
                active_invocation_id=invocation.invocation_id,
                speaking=False,
            )
            snapshot = self._snapshot
            token = self._active_token
        self._presenter.render(snapshot)
        return token

    def update(self, invocation_id: str, status: SessionStatus, **changes: object) -> SessionSnapshot | None:
        with self._lock:
            if self._snapshot.active_invocation_id != invocation_id or self._active_token.is_cancelled:
                return None
            self._snapshot = self._snapshot.evolve(status=status, **changes)
            snapshot = self._snapshot
        self._presenter.render(snapshot)
        return snapshot

    def complete(
        self,
        invocation: ActionInvocation,
        action: ResolvedAction,
        document: InputDocument,
        result_text: str,
        available_actions: tuple[str, ...],
        presentation: PresentationDocument | None = None,
    ) -> SessionSnapshot | None:
        with self._lock:
            if self._snapshot.active_invocation_id != invocation.invocation_id or self._active_token.is_cancelled:
                return None
            kept = self._snapshot.steps[: self._snapshot.displayed_step_index + 1]
            step = WorkflowStep(
                step_id=invocation.invocation_id,
                action_id=action.id,
                title=action.name,
                input_text=document.text,
                result_text=result_text,
                output_profile=action.output_profile,
                parent_step_id=invocation.parent_step_id,
                press_type=invocation.press_type,
                presentation=presentation,
            )
            steps = (*kept, step)
            self._snapshot = self._snapshot.evolve(
                status=SessionStatus.COMPLETED,
                status_text="Completed",
                content=result_text,
                original_input=document.text,
                source_preview=_source_preview(document),
                available_actions=available_actions,
                steps=steps,
                displayed_step_index=len(steps) - 1,
                active_invocation_id=None,
                can_navigate_back=len(steps) > 1,
                presentation=presentation,
            )
            snapshot = self._snapshot
        self._presenter.render(snapshot)
        return snapshot

    def fail(self, invocation_id: str, message: str) -> SessionSnapshot | None:
        with self._lock:
            if self._snapshot.active_invocation_id != invocation_id:
                return None
            self._snapshot = self._snapshot.evolve(
                status=SessionStatus.FAILED,
                status_text="Failed",
                error=message,
                active_invocation_id=None,
                available_actions=self._snapshot.available_actions if self._snapshot.steps else (),
            )
            snapshot = self._snapshot
        self._presenter.render(snapshot)
        return snapshot

    def cancel_active(self) -> None:
        with self._lock:
            self._active_token.cancel()
            if self._snapshot.active_invocation_id is None:
                return
            self._snapshot = self._snapshot.evolve(active_invocation_id=None)

    def navigate_back(self) -> SessionSnapshot | None:
        with self._lock:
            if self._snapshot.displayed_step_index <= 0:
                return None
            index = self._snapshot.displayed_step_index - 1
            step = self._snapshot.steps[index]
            self._snapshot = self._snapshot.evolve(
                status=SessionStatus.COMPLETED,
                title=step.title,
                action_id=step.action_id,
                content=step.result_text,
                original_input=step.input_text,
                error="",
                displayed_step_index=index,
                can_navigate_back=index > 0,
                presentation=step.presentation,
            )
            snapshot = self._snapshot
        self._presenter.render(snapshot)
        return snapshot

    def toggle_pin(self) -> SessionSnapshot:
        with self._lock:
            self._snapshot = self._snapshot.evolve(pinned=not self._snapshot.pinned)
            snapshot = self._snapshot
        self._presenter.render(snapshot)
        return snapshot

    def set_speaking(self, speaking: bool) -> SessionSnapshot:
        with self._lock:
            self._snapshot = self._snapshot.evolve(speaking=speaking)
            snapshot = self._snapshot
        self._presenter.render(snapshot)
        return snapshot

    def cancel(self) -> SessionSnapshot | None:
        self.cancel_active()
        with self._lock:
            self._snapshot = self._snapshot.evolve(status=SessionStatus.CANCELLED, status_text="Cancelled")
            snapshot = self._snapshot
        self._presenter.render(snapshot)
        return snapshot

    def close(self) -> SessionSnapshot | None:
        self.cancel_active()
        with self._lock:
            self._snapshot = self._snapshot.evolve(status=SessionStatus.CLOSED, status_text="Closed")
            snapshot = self._snapshot
        self._presenter.render(snapshot)
        return snapshot


def _source_preview(document: InputDocument, limit: int = 90) -> str:
    compact = " ".join(document.text.split())
    if len(compact) > limit:
        compact = f"{compact[: limit - 1]}..."
    return f"{document.source.replace('_', ' ').title()}: {compact}"
