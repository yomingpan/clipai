from pathlib import Path


def test_capture_timing_has_one_owner_outside_runtime() -> None:
    runtime = Path("ClipAI/app/runtime_voice_input.py").read_text(encoding="utf-8")
    timing = Path("ClipAI/app/voice_capture_timing.py").read_text(encoding="utf-8")

    assert "VoiceCaptureTiming(" in runtime
    assert "self._timing.observe(transition.projection)" in runtime
    assert "_VoiceDeadlineScheduler" not in runtime
    assert "_press_deadlines" not in runtime
    assert "_capture_deadlines" not in runtime
    assert "_silence_watchdogs" not in runtime
    assert '"deadline"' in timing
    assert '"countdown"' in timing
    assert '"silence"' in timing
    assert '"finalize"' in timing
