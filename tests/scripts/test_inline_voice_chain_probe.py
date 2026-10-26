import hashlib
import json

from scripts.probe_inline_voice_chain import _reference, summarize


def test_voice_chain_probe_accepts_only_hash_matched_fixed_phrase(tmp_path) -> None:
    audio = tmp_path / "fixed.wav"
    audio.write_bytes(b"fixture")
    (tmp_path / "manifest.json").write_text(json.dumps({"fixtures": [{
        "file": "fixed.wav", "sha256": hashlib.sha256(b"fixture").hexdigest(),
        "phrase": "你好",
    }]}), encoding="utf-8")

    assert _reference(audio) == "你好"
    audio.write_bytes(b"different")
    assert _reference(audio) == ""


def test_voice_chain_probe_reports_audio_and_literal_error_without_transcript() -> None:
    events = [
        (1, {"kind": "test_loaded"}),
        (2, {"kind": "setup_ready"}),
        (3, {"kind": "listening"}),
        (9, {"kind": "audio_level", "level": 0.9}),
        (12, {"kind": "audio_level", "level": 0.4}),
        (16, {"kind": "interim", "text": "secret interim"}),
        (18, {"kind": "final", "text": "您好"}),
        (19, {"kind": "ended"}),
    ]

    report = summarize(events, playback=(10, 15), reference="你好", fixture_sha256="a" * 64)

    assert report["status"] == "pass"
    assert report["playback_audio_level_samples"] == 1
    assert report["playback_peak_audio_level"] == 0.4
    assert report["literal_character_errors"] == 1
    assert report["literal_character_comparison_status"] == "measured"
    assert report["event_counts"]["interim"] == 1
    assert "您好" not in str(report)
    assert "secret interim" not in str(report)
    assert report["microphone_input_independently_confirmed"] is False
    assert report["browser_error_codes"] == []


def test_voice_chain_probe_does_not_treat_audio_level_as_transcription() -> None:
    events = [
        (1, {"kind": "test_loaded"}),
        (2, {"kind": "setup_ready"}),
        (3, {"kind": "listening"}),
        (12, {"kind": "audio_level", "level": 0.8}),
        (20, {"kind": "ended"}),
    ]

    report = summarize(events, playback=(10, 15), reference="你好", fixture_sha256="b" * 64)

    assert report["status"] == "fail"
    assert report["reason_code"] == "no_final_transcript"
    assert report["event_counts"]["final"] == 0
    assert report["literal_character_error_rate"] is None
    assert report["literal_character_comparison_status"] == "not_observed"


def test_voice_chain_probe_preserves_bounded_browser_error_cause_without_text() -> None:
    report = summarize([
        (1, {"kind": "test_loaded"}),
        (2, {"kind": "setup_ready"}),
        (3, {"kind": "listening"}),
        (4, {"kind": "probe_recognition_error", "code": "network", "text": "private"}),
        (5, {"kind": "ended"}),
    ], playback=(3, 5), reference="你好", fixture_sha256="c" * 64)

    assert report["status"] == "fail"
    assert report["browser_error_codes"] == ["network"]
    assert "private" not in str(report)


def test_voice_chain_probe_requires_observed_playback_even_with_final_text() -> None:
    report = summarize([
        (1, {"kind": "test_loaded"}),
        (2, {"kind": "setup_ready"}),
        (3, {"kind": "listening"}),
        (4, {"kind": "final", "text": "你好"}),
        (5, {"kind": "ended"}),
    ], playback=None, reference="你好", fixture_sha256="d" * 64)

    assert report["status"] == "blocked"
    assert report["reason_code"] == "audio_playback_unavailable"
