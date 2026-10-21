"""Testable destination policy for explicit Voice capture requests."""

from __future__ import annotations

from typing import Protocol

from ClipAI.core.state import SessionSnapshot, SessionStatus
from ClipAI.core.voice import VoiceCaptureAdmission, VoiceCaptureIntent, VoiceCaptureSurfaceContext, VoiceDraftTarget, VoiceFollowUpTarget


class VoiceCaptureEnvironment(Protocol):
    """Read-only workflow facts with one explicit attention request."""

    def voice_capture_presentation(self, workflow_id: str) -> str | None: ...
    def voice_capture_visible_workflow(self) -> tuple[str, SessionSnapshot] | None: ...
    def voice_capture_foreground_id(self) -> str | None: ...
    def voice_capture_snapshot(self, workflow_id: str) -> SessionSnapshot | None: ...
    def voice_capture_surface_context(self, workflow_id: str) -> VoiceCaptureSurfaceContext | None: ...
    def voice_capture_review_target(self, workflow_id: str, context: VoiceCaptureSurfaceContext | None = None) -> VoiceDraftTarget | None: ...
    def request_voice_capture_attention(self, workflow_id: str) -> None: ...


class VoiceCaptureAdmissionPolicy:
    def __init__(self, environment: VoiceCaptureEnvironment) -> None:
        self._environment = environment

    def decide(self, intent: VoiceCaptureIntent) -> VoiceCaptureAdmission:
        env = self._environment
        if intent.trigger == "popup":
            workflow_id = intent.workflow_id
            if workflow_id is None:
                return VoiceCaptureAdmission("rejected")
            if env.voice_capture_presentation(workflow_id) != "visible":
                return VoiceCaptureAdmission("rejected", workflow_id=workflow_id)
            snapshot = env.voice_capture_snapshot(workflow_id)
            if snapshot is None:
                return VoiceCaptureAdmission("rejected", workflow_id=workflow_id)
            return self._for_visible(intent, workflow_id, snapshot)
        visible = env.voice_capture_visible_workflow()
        if visible is not None and env.voice_capture_foreground_id() == visible[0]:
            return self._for_visible(intent, *visible)
        if intent.focused_surface is not None:
            if intent.focused_surface.kind != "workflow":
                return VoiceCaptureAdmission("rejected", message="Close the active ClipAI window, then try again.")
            target = env.voice_capture_review_target(intent.focused_surface.surface_id)
            if target is not None:
                return VoiceCaptureAdmission("voice_review", workflow_id=intent.focused_surface.surface_id, target=target)
        return VoiceCaptureAdmission("create")

    def _for_visible(self, intent: VoiceCaptureIntent, workflow_id: str, snapshot: SessionSnapshot) -> VoiceCaptureAdmission:
        env = self._environment
        shortcut = intent.trigger == "shortcut"
        if shortcut and intent.active_voice_workflow_id == workflow_id:
            env.request_voice_capture_attention(workflow_id)
            return VoiceCaptureAdmission("continue", workflow_id=workflow_id)
        focused_surface = intent.focused_surface
        if shortcut and focused_surface is None:
            return VoiceCaptureAdmission("rejected", workflow_id=workflow_id, message="請先點選目前的 ClipAI 視窗再使用語音輸入，或關閉視窗後開始新的語音輸入。")
        if shortcut:
            assert focused_surface is not None
            if focused_surface.kind != "workflow" or focused_surface.surface_id != workflow_id:
                return VoiceCaptureAdmission("rejected", workflow_id=workflow_id, message="請先點選目前的 ClipAI 視窗再使用語音輸入。")
        provider_active = snapshot.active_invocation_id is not None or snapshot.status in {
            SessionStatus.READING_INPUT,
            SessionStatus.PREPARING_REQUEST,
            SessionStatus.REQUESTING_PROVIDER,
            SessionStatus.PROCESSING_RESULT,
        }
        if provider_active:
            return VoiceCaptureAdmission("rejected", workflow_id=workflow_id, message="AI 正在回答，完成後再追問。" if shortcut else "")
        context = env.voice_capture_surface_context(workflow_id)
        if shortcut and context is not None and context.follow_up_requested:
            return VoiceCaptureAdmission("follow_up", workflow_id=workflow_id, target=VoiceFollowUpTarget(workflow_id))
        if snapshot.status is SessionStatus.VOICE_REVIEW:
            target = env.voice_capture_review_target(workflow_id, context)
            if target is not None:
                return VoiceCaptureAdmission("voice_review", workflow_id=workflow_id, target=target)
            return VoiceCaptureAdmission("rejected", workflow_id=workflow_id)
        if (
            snapshot.status in {SessionStatus.CONTEXT_QUESTION, SessionStatus.COMPLETED, SessionStatus.FAILED, SessionStatus.STOPPED}
            and (snapshot.status is SessionStatus.CONTEXT_QUESTION or snapshot.displayed_step_index >= 0)
            and "follow_up" in snapshot.available_actions
        ):
            return VoiceCaptureAdmission("follow_up", workflow_id=workflow_id, target=VoiceFollowUpTarget(workflow_id))
        return VoiceCaptureAdmission("rejected", workflow_id=workflow_id, message="這份內容目前無法使用 Follow-up。" if shortcut else "")
