from __future__ import annotations

from ClipAI.app.runtime_workflows import VoiceCaptureAdmission, VoiceCaptureIntent
from ClipAI.services.voice_capture_admission import VoiceCaptureAdmissionPolicy
from ClipAI.core.models import ControlSurfaceRef
from ClipAI.core.state import SessionSnapshot, SessionStatus
from ClipAI.core.voice import VoiceCaptureSurfaceContext, VoiceDraftTarget, VoiceFollowUpTarget


def snapshot(status: SessionStatus, **changes) -> SessionSnapshot:
    base = SessionSnapshot("workflow-1", 0, status, "voice_input", "Voice Input", "model")
    return base.evolve(**changes)


class Environment:
    def __init__(self, state: SessionSnapshot) -> None:
        self.state = state
        self.presentation = "visible"
        self.foreground = "workflow-1"
        self.context = None
        self.review_target = None
        self.attentions = []

    def voice_capture_presentation(self, workflow_id): return self.presentation if workflow_id == "workflow-1" else None
    def voice_capture_visible_workflow(self): return ("workflow-1", self.state) if self.presentation == "visible" else None
    def voice_capture_foreground_id(self): return self.foreground
    def voice_capture_snapshot(self, workflow_id): return self.state if workflow_id == "workflow-1" else None
    def voice_capture_surface_context(self, workflow_id): return self.context
    def voice_capture_review_target(self, workflow_id, context=None): return self.review_target
    def request_voice_capture_attention(self, workflow_id): self.attentions.append(workflow_id)


def test_popup_rejects_nonvisible_workflow_before_other_policy() -> None:
    env = Environment(snapshot(SessionStatus.COMPLETED))
    env.presentation = "headless"
    assert VoiceCaptureAdmissionPolicy(env).decide(VoiceCaptureIntent("popup", workflow_id="workflow-1")) == VoiceCaptureAdmission("rejected", workflow_id="workflow-1")


def test_shortcut_requires_focus_and_rejects_active_provider() -> None:
    env = Environment(snapshot(SessionStatus.COMPLETED, available_actions=("follow_up",)))
    policy = VoiceCaptureAdmissionPolicy(env)
    assert policy.decide(VoiceCaptureIntent("shortcut")) == VoiceCaptureAdmission("rejected", workflow_id="workflow-1", message="請先點選目前的 ClipAI 視窗再使用語音輸入，或關閉視窗後開始新的語音輸入。")
    env.state = snapshot(SessionStatus.REQUESTING_PROVIDER)
    assert policy.decide(VoiceCaptureIntent("shortcut", focused_surface=ControlSurfaceRef("workflow-1", "workflow"))) == VoiceCaptureAdmission("rejected", workflow_id="workflow-1", message="AI 正在回答，完成後再追問。")


def test_shortcut_follow_up_and_voice_review_match_existing_destinations() -> None:
    env = Environment(snapshot(SessionStatus.COMPLETED, available_actions=("follow_up",), displayed_step_index=0))
    policy = VoiceCaptureAdmissionPolicy(env)
    intent = VoiceCaptureIntent("shortcut", focused_surface=ControlSurfaceRef("workflow-1", "workflow"))
    assert policy.decide(intent).target == VoiceFollowUpTarget("workflow-1")
    env.state = snapshot(SessionStatus.VOICE_REVIEW)
    env.review_target = VoiceDraftTarget("workflow-1", 0, None, 0, 0)
    assert policy.decide(intent).target == env.review_target


def test_shortcut_uses_raw_foreground_identity_before_visible_policy() -> None:
    env = Environment(snapshot(SessionStatus.COMPLETED))
    env.foreground = "other"
    policy = VoiceCaptureAdmissionPolicy(env)
    assert policy.decide(VoiceCaptureIntent("shortcut", focused_surface=ControlSurfaceRef("panel", "entry_panel"))) == VoiceCaptureAdmission("rejected", message="Close the active ClipAI window, then try again.")
