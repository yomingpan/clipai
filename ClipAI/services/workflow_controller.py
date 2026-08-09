from __future__ import annotations

import threading
from dataclasses import replace

from ClipAI.core.models import ActionInvocation, InputDocument, PresentationDocument, ResolvedAction, WorkflowStep
from ClipAI.core.ports import ResultPresenter
from ClipAI.core.state import CancellationToken, SessionSnapshot, SessionStatus
from ClipAI.core.voice import VoiceDraftTarget


class WorkflowController:
    """Single owner for one popup workflow and its linear successful-step history."""

    def __init__(self, initial: SessionSnapshot, presenter: ResultPresenter) -> None:
        self._snapshot = initial
        self._presenter = presenter
        self._lock = threading.RLock()
        self._active_token = CancellationToken()
        self._feedback_step_ids: set[str] = set()
        self._feedback_operations: dict[str, str] = {}
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
                action_feedback_contract=action.feedback_contract,
                input_source=(
                    "selection or clipboard" if action.input_mode == "selection_or_clipboard"
                    else "clipboard screenshot" if action.input_mode == "clipboard_image"
                    else "clipboard"
                ),
                feedback_state="idle",
                feedback_step_id="",
                feedback_operation_id="",
                feedback_message="",
                show_guidance_hint=False,
                result_completeness="none",
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

    def append_provider_text(self, invocation_id: str, text: str) -> SessionSnapshot | None:
        if not text:
            return self.snapshot
        with self._lock:
            if self._snapshot.active_invocation_id != invocation_id or self._active_token.is_cancelled:
                return None
            content = text if self._snapshot.result_completeness == "none" else f"{self._snapshot.content}{text}"
            self._snapshot = self._snapshot.evolve(
                content=content,
                status=SessionStatus.REQUESTING_PROVIDER,
                status_text="Receiving response...",
                result_completeness="partial",
                available_actions=("copy",),
            )
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
        *,
        provider: str = "",
        model: str = "",
        show_guidance_hint: bool = False,
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
                input_source=document.source,
                feedback_contract=action.feedback_contract,
                action_version=action.version_id,
                provider=provider,
                model=model,
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
                action_feedback_contract=step.feedback_contract,
                input_source=document.source,
                feedback_state="idle",
                feedback_step_id="",
                feedback_operation_id="",
                feedback_message="",
                show_guidance_hint=show_guidance_hint,
                result_completeness="complete",
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
                available_actions=(
                    ("copy",)
                    if self._snapshot.result_completeness == "partial"
                    else self._snapshot.available_actions if self._snapshot.steps else ()
                ),
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

    def stop_active(self) -> str | None:
        with self._lock:
            invocation_id = self._snapshot.active_invocation_id
            if invocation_id is None:
                return None
            self._active_token.cancel()
            if self._snapshot.displayed_step_index >= 0:
                self._snapshot = self._snapshot.evolve(
                    status=SessionStatus.COMPLETED,
                    status_text="Stopped",
                    active_invocation_id=None,
                    speaking=False,
                )
            else:
                self._snapshot = self._snapshot.evolve(
                    status=SessionStatus.STOPPED,
                    status_text="Stopped",
                    active_invocation_id=None,
                    speaking=False,
                )
            snapshot = self._snapshot
        self._presenter.render(snapshot)
        return invocation_id

    def navigate_back(self) -> SessionSnapshot | None:
        with self._lock:
            if self._snapshot.voice_origin is not None and self._snapshot.displayed_step_index == 0:
                origin = self._snapshot.voice_origin
                self._snapshot = self._snapshot.evolve(
                    status=SessionStatus.VOICE_REVIEW,
                    title="Voice Input",
                    action_id="voice_input",
                    content=origin.text,
                    original_input="",
                    source_preview="Voice Input draft",
                    error="",
                    displayed_step_index=-1,
                    can_navigate_back=False,
                    presentation=None,
                    action_feedback_contract=None,
                    input_source="voice_transcript",
                    feedback_state="idle",
                    feedback_step_id="",
                    feedback_operation_id="",
                    feedback_message="",
                    show_guidance_hint=False,
                    result_completeness="complete",
                    available_actions=("copy", "paste", "follow_up"),
                )
                snapshot = self._snapshot
                self._presenter.render(snapshot)
                return snapshot
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
                action_feedback_contract=step.feedback_contract,
                input_source=step.input_source,
                feedback_state="succeeded" if step.step_id in self._feedback_step_ids else "idle",
                feedback_step_id=step.step_id if step.step_id in self._feedback_step_ids else "",
                feedback_operation_id="",
                feedback_message="已記錄回饋" if step.step_id in self._feedback_step_ids else "",
                show_guidance_hint=False,
            )
            snapshot = self._snapshot
        self._presenter.render(snapshot)
        return snapshot

    def freeze_voice_insertion(self, selection_start: int, selection_end: int) -> VoiceDraftTarget | None:
        """Freeze the Voice-origin insertion range before a capture begins."""
        with self._lock:
            origin = self._snapshot.voice_origin
            if (
                origin is None
                or self._snapshot.status is not SessionStatus.VOICE_REVIEW
                or self._snapshot.active_invocation_id is not None
                or selection_start < 0
                or selection_end < selection_start
                or selection_end > len(origin.text)
            ):
                return None
            return VoiceDraftTarget(
                self._snapshot.session_id,
                origin.revision,
                origin.paste_target,
                selection_start,
                selection_end,
            )

    def apply_voice_finalization(self, target: VoiceDraftTarget, text: str) -> SessionSnapshot | None:
        """Apply one controller-settled capture only to its frozen Voice origin."""
        if not text.strip():
            return None
        with self._lock:
            origin = self._snapshot.voice_origin
            if (
                origin is None
                or target.workflow_id != self._snapshot.session_id
                or target.expected_revision != origin.revision
                or target.paste_target != origin.paste_target
                or target.selection_end > len(origin.text)
            ):
                return None
            content = f"{origin.text[:target.selection_start]}{text}{origin.text[target.selection_end:]}"
            self._snapshot = self._snapshot.evolve(
                status=SessionStatus.VOICE_REVIEW,
                title="Voice Input",
                action_id="voice_input",
                content=content,
                original_input="",
                source_preview="Voice Input draft",
                error="",
                active_invocation_id=None,
                displayed_step_index=-1,
                can_navigate_back=False,
                presentation=None,
                action_feedback_contract=None,
                input_source="voice_transcript",
                feedback_state="idle",
                feedback_step_id="",
                feedback_operation_id="",
                feedback_message="",
                show_guidance_hint=False,
                result_completeness="complete",
                available_actions=("copy", "paste", "follow_up"),
                voice_origin=replace(origin, text=content, revision=origin.revision + 1),
            )
            snapshot = self._snapshot
        self._presenter.render(snapshot)
        return snapshot

    def edit_voice_draft(self, expected_revision: int, text: str) -> SessionSnapshot | None:
        with self._lock:
            origin = self._snapshot.voice_origin
            if (
                origin is None
                or self._snapshot.status is not SessionStatus.VOICE_REVIEW
                or origin.revision != expected_revision
            ):
                return None
            self._snapshot = self._snapshot.evolve(
                content=text,
                voice_origin=replace(origin, text=text, revision=origin.revision + 1),
            )
            snapshot = self._snapshot
        self._presenter.render(snapshot)
        return snapshot

    def begin_feedback(self, step_id: str, operation_id: str) -> WorkflowStep | None:
        with self._lock:
            if self._snapshot.status != SessionStatus.COMPLETED or self._snapshot.displayed_step_index < 0:
                return None
            step = self._snapshot.steps[self._snapshot.displayed_step_index]
            if step.step_id != step_id or step.feedback_contract is None or step_id in self._feedback_step_ids:
                return None
            if step_id in self._feedback_operations:
                return None
            self._feedback_operations[step_id] = operation_id
            self._snapshot = self._snapshot.evolve(
                feedback_state="pending",
                feedback_step_id=step_id,
                feedback_operation_id=operation_id,
                feedback_message="正在儲存回饋…",
            )
            snapshot = self._snapshot
        self._presenter.render(snapshot)
        return step

    def complete_feedback(self, step_id: str, operation_id: str, error: str = "") -> SessionSnapshot | None:
        with self._lock:
            if self._feedback_operations.get(step_id) != operation_id:
                return None
            self._feedback_operations.pop(step_id, None)
            if not error:
                self._feedback_step_ids.add(step_id)
            if (
                self._snapshot.feedback_step_id != step_id
                or self._snapshot.feedback_operation_id != operation_id
                or self._snapshot.displayed_step_index < 0
                or self._snapshot.steps[self._snapshot.displayed_step_index].step_id != step_id
            ):
                return None
            if error:
                self._snapshot = self._snapshot.evolve(
                    feedback_state="failed",
                    feedback_message=error,
                )
            else:
                self._snapshot = self._snapshot.evolve(
                    feedback_state="succeeded",
                    feedback_message="已記錄回饋",
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
