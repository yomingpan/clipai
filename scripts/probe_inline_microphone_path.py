"""Check whether a SHA-matched fixed WAV reaches the default Windows microphone.

Records only bounded signal statistics. Microphone samples are never written to disk.
This is an acoustic-path probe, not a transcription or ClipAI shortcut test.
"""

from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import time
import wave
import winsound


SAMPLE_RATE = 22050
FRAME_SAMPLES = 220
MAX_RECORD_SECONDS = 9


class WaveFormat(ctypes.Structure):
    _fields_ = [
        ("wFormatTag", wintypes.WORD), ("nChannels", wintypes.WORD),
        ("nSamplesPerSec", wintypes.DWORD), ("nAvgBytesPerSec", wintypes.DWORD),
        ("nBlockAlign", wintypes.WORD), ("wBitsPerSample", wintypes.WORD),
        ("cbSize", wintypes.WORD),
    ]


class WaveHeader(ctypes.Structure):
    _fields_ = [
        ("lpData", ctypes.c_void_p), ("dwBufferLength", wintypes.DWORD),
        ("dwBytesRecorded", wintypes.DWORD), ("dwUser", ctypes.c_size_t),
        ("dwFlags", wintypes.DWORD), ("dwLoops", wintypes.DWORD),
        ("lpNext", ctypes.c_void_p), ("reserved", ctypes.c_size_t),
    ]


def fixture_digest(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = json.loads((path.parent / "manifest.json").read_text(encoding="utf-8-sig"))
    if not any(
        isinstance(item, dict) and item.get("file") == path.name and item.get("sha256") == digest
        for item in manifest.get("fixtures", [])
    ):
        raise ValueError("WAV does not match the fixed fixture manifest")
    return digest


def envelope(samples: tuple[int, ...], frame_samples: int = FRAME_SAMPLES) -> list[float]:
    return [
        math.sqrt(sum(value * value for value in samples[index:index + frame_samples]) / frame_samples)
        for index in range(0, len(samples) - frame_samples + 1, frame_samples)
    ]


def best_envelope_correlation(reference: list[float], captured: list[float]) -> tuple[float, int]:
    """Compare changing signal energy, allowing acoustic startup delay."""
    if len(reference) < 10 or len(captured) < len(reference):
        return 0.0, -1
    best, offset = 0.0, -1
    ref_mean = sum(reference) / len(reference)
    centered_ref = [value - ref_mean for value in reference]
    ref_energy = sum(value * value for value in centered_ref)
    for start in range(len(captured) - len(reference) + 1):
        segment = captured[start:start + len(reference)]
        segment_mean = sum(segment) / len(segment)
        centered = [value - segment_mean for value in segment]
        denominator = math.sqrt(ref_energy * sum(value * value for value in centered))
        score = sum(a * b for a, b in zip(centered_ref, centered)) / denominator if denominator else 0.0
        if score > best:
            best, offset = score, start
    return best, offset


def capture_while_playing(path: Path, duration_seconds: float) -> tuple[bytes, int]:
    winmm = ctypes.WinDLL("winmm")
    handle = ctypes.c_void_p()
    fmt = WaveFormat(1, 1, SAMPLE_RATE, SAMPLE_RATE * 2, 2, 16, 0)
    winmm.waveInOpen.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_uint, ctypes.POINTER(WaveFormat), ctypes.c_size_t, ctypes.c_size_t, ctypes.c_uint]
    winmm.waveInOpen.restype = wintypes.UINT
    winmm.waveInPrepareHeader.argtypes = [ctypes.c_void_p, ctypes.POINTER(WaveHeader), wintypes.UINT]
    winmm.waveInAddBuffer.argtypes = [ctypes.c_void_p, ctypes.POINTER(WaveHeader), wintypes.UINT]
    winmm.waveInStart.argtypes = [ctypes.c_void_p]
    winmm.waveInReset.argtypes = [ctypes.c_void_p]
    winmm.waveInUnprepareHeader.argtypes = [ctypes.c_void_p, ctypes.POINTER(WaveHeader), wintypes.UINT]
    winmm.waveInClose.argtypes = [ctypes.c_void_p]
    error = winmm.waveInOpen(ctypes.byref(handle), 0xFFFFFFFF, ctypes.byref(fmt), 0, 0, 0)
    if error:
        raise OSError(f"waveInOpen failed: {error}")
    buffer = ctypes.create_string_buffer(int(SAMPLE_RATE * 2 * min(duration_seconds, MAX_RECORD_SECONDS)))
    header = WaveHeader(ctypes.cast(buffer, ctypes.c_void_p), len(buffer), 0, 0, 0, 0, None, 0)
    prepared = False
    try:
        error = winmm.waveInPrepareHeader(handle, ctypes.byref(header), ctypes.sizeof(header))
        if error:
            raise OSError(f"waveInPrepareHeader failed: {error}")
        prepared = True
        error = winmm.waveInAddBuffer(handle, ctypes.byref(header), ctypes.sizeof(header))
        if error:
            raise OSError(f"waveInAddBuffer failed: {error}")
        error = winmm.waveInStart(handle)
        if error:
            raise OSError(f"waveInStart failed: {error}")
        time.sleep(0.5)
        winsound.PlaySound(str(path), winsound.SND_FILENAME)
        time.sleep(0.4)
        winmm.waveInReset(handle)
        count = header.dwBytesRecorded & ~1
        return bytes(buffer[:count]), count // 2
    finally:
        winmm.waveInReset(handle)
        if prepared:
            winmm.waveInUnprepareHeader(handle, ctypes.byref(header), ctypes.sizeof(header))
        winmm.waveInClose(handle)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = args.audio_file.resolve()
    digest = fixture_digest(source)
    with wave.open(str(source), "rb") as fixture:
        if fixture.getnchannels() != 1 or fixture.getsampwidth() != 2 or fixture.getframerate() != SAMPLE_RATE:
            parser.error("fixed WAV must be mono 16-bit 22050 Hz PCM")
        reference = struct.unpack("<" + "h" * fixture.getnframes(), fixture.readframes(fixture.getnframes()))
    recorded_bytes, count = capture_while_playing(source, len(reference) / SAMPLE_RATE + 1.2)
    captured = struct.unpack("<" + "h" * count, recorded_bytes)
    reference_levels, captured_levels = envelope(reference), envelope(captured)
    correlation, offset = best_envelope_correlation(reference_levels, captured_levels)
    preplay = captured_levels[:40]
    baseline = math.sqrt(sum(level * level for level in preplay) / len(preplay)) if preplay else 0.0
    peak = max(captured_levels, default=0.0)
    report = {
        "schema_version": 1,
        "scope": "independent_default_microphone_acoustic_path",
        "fixture_sha256": digest,
        "sample_rate_hz": SAMPLE_RATE,
        "capture_seconds": round(count / SAMPLE_RATE, 2),
        "baseline_rms": round(baseline, 1),
        "peak_rms": round(peak, 1),
        "best_energy_envelope_correlation": round(correlation, 3),
        "best_offset_seconds": round(offset * FRAME_SAMPLES / SAMPLE_RATE, 2) if offset >= 0 else None,
        "status": "pass" if count > SAMPLE_RATE and correlation >= 0.5 and peak > baseline * 2 else "not_confirmed",
        "raw_audio_saved": False,
        "limits": "Default WaveIn microphone only; does not prove WebView used it or recognized speech.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
