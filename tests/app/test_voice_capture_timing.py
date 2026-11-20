from __future__ import annotations

from ClipAI.core.commands import VoiceCaptureTimeout, VoiceFinalizeWatchdogExpired
from ClipAI.core.voice import VoiceCaptureId, VoiceCapturePhase, VoiceCapabilityPhase, VoiceProjection
from ClipAI.app.voice_capture_timing import VoiceCaptureTiming


class Timer:
    def __init__(self, callback):
        self.callback = callback
        self.cancelled = False

    def cancel(self):
        self.cancelled = True


def test_capture_deadline_starts_only_after_listening_and_finalize_watchdog_survives_transition():
    timers = []
    sent = []

    def schedule(delay, callback):
        timer = Timer(callback)
        timers.append((delay, timer))
        return timer

    timing = VoiceCaptureTiming(schedule, lambda: 0.0, sent.append, lambda _: None)
    capture = VoiceCaptureId("voice-1")
    timing.observe(VoiceProjection(VoiceCapabilityPhase.READY, "zh-TW", capture, VoiceCapturePhase.STARTING))
    assert timers == []
    timing.observe(VoiceProjection(VoiceCapabilityPhase.READY, "zh-TW", capture, VoiceCapturePhase.LISTENING))
    assert any(delay == 120 for delay, _ in timers)
    timing.observe(VoiceProjection(VoiceCapabilityPhase.READY, "zh-TW", capture, VoiceCapturePhase.FINALIZING))
    assert any(delay == 6 and not timer.cancelled for delay, timer in timers)
    assert all(timer.cancelled for delay, timer in timers if delay == 120)
    next(timer for delay, timer in timers if delay == 6).callback()
    assert sent[-1] == VoiceFinalizeWatchdogExpired(capture)
