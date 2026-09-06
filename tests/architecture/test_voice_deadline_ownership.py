from pathlib import Path


def test_voice_deadlines_use_separate_typed_scheduler_instances() -> None:
    source = Path("ClipAI/app/runtime_voice_input.py").read_text(encoding="utf-8")

    assert "_VoiceDeadlineScheduler[ShortcutPressId]" in source
    assert "_VoiceDeadlineScheduler[VoiceCaptureId]" in source
    assert "_capture_deadlines_by_id" not in source
    assert "_countdown_watchdogs" not in source
    assert "dict[ShortcutPressId, object]" not in source
