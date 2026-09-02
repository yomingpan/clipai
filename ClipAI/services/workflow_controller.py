from __future__ import annotations

from collections.abc import Callable
import threading

from ClipAI.core.models import ActionInvocation, InputDocument, PresentationDocument, ResolvedAction, WorkflowStep
from ClipAI.core.ports import ResultPresenter
from ClipAI.core.state import CancellationToken, SessionSnapshot, SessionStatus
from ClipAI.core.voice import VoiceCaptureDestination, VoiceCaptureId, VoiceDraftTarget, VoiceFollowUpTarget, VoiceProjection
from ClipAI.services import voice_draft, voice_follow_up


CONTEXTUAL_SOURCE_MAX_CHARS = 40_000


class WorkflowController:
    """Single owner for one popup workflow and its linear successful-step history."""

    def __init__(
        self,
        initial: SessionSnapshot,
        presenter: ResultPresenter,
        *,
        on_step_accepted: Callable[[str, str], None] | None = None,
    ) -> None:
        self._snapshot = initial
        self._presenter = presenter
        self._lock = threading.RLock()
        self._active_token = CancellationToken()
        self._context_capture_token = CancellationToken()
        self._feedback_step_ids: set[str] = set()
        self._feedback_operations: dict[str, str] = {}
        self._on_step_accepted = on_step_accepted
        self._presenter.render(initial)

    @property
    def snapshot(self) -> SessionSnapshot:
        with self._lock:
            return self._snapshot

    @property
    def cancellation(self) -> CancellationToken:
        with self._lock:
            return self._active_token

    def begin_contextual_source_capture(self, capture_id: str) -> CancellationToken:
        with self._lock:
            self._context_capture_token.cancel()
            self._context_capture_token = CancellationToken()
            self._snapshot = self._snapshot.evolve(
                status=SessionStatus.READING_INPUT,
                action_id="contextual_question",
                title="問這段",
                status_text="正在讀取選取內容…",
                content="",
                error="",
                available_actions=(),
                original_input="",
                input_source="selection or clipboard",
                contextual_source_capture_id=capture_id,
                contextual_source_text="",
                contextual_source_kind="",
                result_completeness="none",
            )
            snapshot = self._snapshot
            token = self._context_capture_token
        self._presenter.render(snapshot)
        return token

    def complete_contextual_source_capture(
        self,
        capture_id: str,
        document: InputDocument,
    ) -> SessionSnapshot | None:
        with self._lock:
            if (
                self._snapshot.contextual_source_capture_id != capture_id
                or self._context_capture_token.is_cancelled
                or document.source not in {"selection", "clipboard"}
            ):
                return None
            if len(document.text) > CONTEXTUAL_SOURCE_MAX_CHARS:
                raise ValueError(
                    f"這段內容太長（{len(document.text):,} 個字元）。請縮小選取範圍後再試一次。"
                )
            self._snapshot = self._snapshot.evolve(
                status=SessionStatus.CONTEXT_QUESTION,
                status_text="想知道什麼？",
                source_preview=_source_preview(document),
                available_actions=("follow_up",),
                original_input=document.text,
                input_source=document.source,
                contextual_source_capture_id=None,
                contextual_source_text=document.text,
                contextual_source_kind=document.source,
                question_composer_revision=self._snapshot.question_composer_revision + 1,
            )
            snapshot = self._snapshot
        self._presenter.render(snapshot)
        return snapshot

    def fail_contextual_source_capture(
        self,
        capture_id: str,
        message: str,
    ) -> SessionSnapshot | None:
        with self._lock:
            if self._snapshot.contextual_source_capture_id != capture_id:
                return None
            self._context_capture_token.cancel()
            self._snapshot = self._snapshot.evolve(
                status=SessionStatus.FAILED,
                status_text="讀取失敗",
                error=message,
                contextual_source_capture_id=None,
                available_actions=(),
            )
            snapshot = self._snapshot
        self._presenter.render(snapshot)
        return snapshot

    def request_question_composer(self) -> SessionSnapshot | None:
        with self._lock:
            if (
                self._snapshot.active_invocation_id is not None
                or self._snapshot.status not in {
                    SessionStatus.CONTEXT_QUESTION,
                    SessionStatus.COMPLETED,
                    SessionStatus.FAILED,
                    SessionStatus.STOPPED,
                    SessionStatus.VOICE_REVIEW,
                }
                or "follow_up" not in self._snapshot.available_actions
            ):
                return None
            self._snapshot = self._snapshot.evolve(
                question_composer_revision=self._snapshot.question_composer_revision + 1,
            )
            snapshot = self._snapshot
        self._presenter.render(snapshot)
        return snapshot

    def stop_contextual_source_capture(self) -> str | None:
        with self._lock:
            capture_id = self._snapshot.contextual_source_capture_id
            if capture_id is None:
                return None
            self._context_capture_token.cancel()
            self._snapshot = self._snapshot.evolve(
                status=SessionStatus.STOPPED,
                status_text="已停止",
                contextual_source_capture_id=None,
                available_actions=(),
            )
            snapshot = self._snapshot
        self._presenter.render(snapshot)
        return capture_id

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
                action_language=action.action_language,
            )
            steps = (*kept, step)
            source_preview = _source_preview(document)
            if (
                action.id == "contextual_question"
                and self._snapshot.contextual_source_text
                and self._snapshot.contextual_source_kind in {"selection", "clipboard"}
            ):
                source_preview = _source_preview(InputDocument(
                    self._snapshot.contextual_source_text,
                    self._snapshot.contextual_source_kind,
                ))
            self._snapshot = self._snapshot.evolve(
                status=SessionStatus.COMPLETED,
                status_text="Completed",
                content=result_text,
                original_input=document.text,
                source_preview=source_preview,
                available_actions=available_actions,
                steps=steps,
                displayed_step_index=len(steps) - 1,
                active_invocation_id=None,
                can_navigate_back=len(steps) > 1 or voice_draft.can_return_to_review(self._snapshot),
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
        if self._on_step_accepted is not None:
            self._on_step_accepted(snapshot.session_id, step.step_id)
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
            self._context_capture_token.cancel()
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
            next_snapshot = voice_draft.return_to_review(self._snapshot)
            if next_snapshot is None:
                if self._snapshot.displayed_step_index <= 0:
                    return None
                index = self._snapshot.displayed_step_index - 1
                step = self._snapshot.steps[index]
                next_snapshot = self._snapshot.evolve(
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
            self._snapshot = next_snapshot
            snapshot = self._snapshot
        self._presenter.render(snapshot)
        return snapshot

    def freeze_voice_insertion(self, selection_start: int, selection_end: int) -> VoiceDraftTarget | None:
        """Freeze the Voice-origin insertion range before a capture begins."""
        with self._lock:
            return voice_draft.freeze_insertion(
                self._snapshot,
                selection_start,
                selection_end,
            )

    def project_voice_capture(self, projection: VoiceProjection) -> SessionSnapshot | None:
        """Project controller-owned capture lifecycle without making it canonical draft state."""
        with self._lock:
            next_snapshot = (
                voice_follow_up.project_capture(self._snapshot, projection)
                if projection.capture_destination is VoiceCaptureDestination.FOLLOW_UP
                else voice_draft.project_capture(self._snapshot, projection)
            )
            if next_snapshot is None:
                return None
            self._snapshot = next_snapshot
            snapshot = self._snapshot
        self._presenter.render(snapshot)
        return snapshot

    def restore_voice_follow_up(
        self,
        capture_id: VoiceCaptureId,
        target: VoiceFollowUpTarget,
        message: str,
    ) -> SessionSnapshot | None:
        with self._lock:
            next_snapshot = voice_follow_up.restore(self._snapshot, capture_id, target, message)
            if next_snapshot is None:
                return None
            self._snapshot = next_snapshot
            snapshot = self._snapshot
        self._presenter.render(snapshot)
        return snapshot

    def apply_voice_follow_up_finalization(
        self,
        capture_id: VoiceCaptureId,
        target: VoiceFollowUpTarget,
        text: str,
    ) -> SessionSnapshot | None:
        with self._lock:
            next_snapshot = voice_follow_up.finalize(self._snapshot, capture_id, target, text)
            if next_snapshot is None:
                return None
            self._snapshot = next_snapshot
            snapshot = self._snapshot
        self._presenter.render(snapshot)
        return snapshot

    def restore_voice_review(self, target: VoiceDraftTarget, message: str) -> SessionSnapshot | None:
        with self._lock:
            next_snapshot = voice_draft.restore_review(self._snapshot, target, message)
            if next_snapshot is None:
                return None
            self._snapshot = next_snapshot
            snapshot = self._snapshot
        self._presenter.render(snapshot)
        return snapshot

    def apply_voice_finalization(self, target: VoiceDraftTarget, text: str) -> SessionSnapshot | None:
        """Apply one controller-settled capture only to its frozen Voice origin."""
        with self._lock:
            next_snapshot = voice_draft.finalize_capture(self._snapshot, target, text)
            if next_snapshot is None:
                return None
            self._snapshot = next_snapshot
            snapshot = self._snapshot
        self._presenter.render(snapshot)
        return snapshot

    def edit_voice_draft(self, expected_revision: int, text: str) -> SessionSnapshot | None:
        with self._lock:
            next_snapshot = voice_draft.edit_draft(
                self._snapshot,
                expected_revision,
                text,
            )
            if next_snapshot is None:
                return None
            self._snapshot = next_snapshot
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
