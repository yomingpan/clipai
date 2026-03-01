from __future__ import annotations


def format_rhythm_indicator(state: str, tempo: float) -> str:
    return f"Rhythm {state} ({tempo:.1f} bpm)"
