import hashlib
import json

import pytest

from scripts.probe_inline_microphone_path import best_envelope_correlation, envelope, fixture_digest


def test_microphone_probe_rejects_audio_without_matching_manifest(tmp_path) -> None:
    audio = tmp_path / "fixed.wav"
    audio.write_bytes(b"fixture")
    (tmp_path / "manifest.json").write_text(json.dumps({"fixtures": [{
        "file": "fixed.wav", "sha256": hashlib.sha256(b"fixture").hexdigest(),
    }]}), encoding="utf-8")

    assert fixture_digest(audio) == hashlib.sha256(b"fixture").hexdigest()
    audio.write_bytes(b"different")
    with pytest.raises(ValueError, match="does not match"):
        fixture_digest(audio)


def test_microphone_probe_locates_delayed_acoustic_envelope() -> None:
    reference = [float((index * 7) % 13 + index % 3) for index in range(25)]
    captured = [0.0] * 7 + reference + [0.0] * 4

    score, offset = best_envelope_correlation(reference, captured)

    assert score == pytest.approx(1.0)
    assert offset == 7
    assert best_envelope_correlation(reference, [0.0] * len(captured)) == (0.0, -1)


def test_microphone_probe_uses_fixed_nonoverlapping_frames() -> None:
    assert envelope((0, 0, 3, 4), frame_samples=2) == [0.0, pytest.approx((12.5) ** 0.5)]
