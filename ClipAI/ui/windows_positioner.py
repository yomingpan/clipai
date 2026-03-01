from __future__ import annotations


def compute_popup_position(screen_w: int, screen_h: int, width: int, height: int) -> tuple[int, int]:
    x = max(0, screen_w - width - 24)
    y = max(0, screen_h - height - 48)
    return x, y
