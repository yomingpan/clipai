from __future__ import annotations

import ctypes
from types import SimpleNamespace

import pytest

from ClipAI.platform import keyboard_state


@pytest.mark.parametrize(
    ("token", "pressed_virtual_key", "expected_queries"),
    [
        ("ctrl", 0x11, [0x11]),
        ("alt", 0xA4, [0x12, 0xA4]),
        ("alt", 0xA5, [0x12, 0xA4, 0xA5]),
        ("x", 0x58, [0x58]),
        ("grave", 0xC0, [0xC0]),
        ("6", 0x36, [0x36]),
        ("6", 0x66, [0x36, 0x66]),
    ],
)
def test_windows_key_state_maps_normalized_hotkey_tokens(
    monkeypatch,
    token: str,
    pressed_virtual_key: int,
    expected_queries: list[int],
) -> None:
    queried_virtual_keys = []

    class FakeUser32:
        def GetAsyncKeyState(self, virtual_key: int) -> int:
            queried_virtual_keys.append(virtual_key)
            return 0x8000 if virtual_key == pressed_virtual_key else 0

    monkeypatch.setattr(keyboard_state.sys, "platform", "win32")
    monkeypatch.setattr(
        ctypes,
        "windll",
        SimpleNamespace(user32=FakeUser32()),
        raising=False,
    )

    assert keyboard_state.windows_key_is_pressed(token) is True
    assert queried_virtual_keys == expected_queries


def test_windows_key_state_returns_unknown_for_unsupported_token(monkeypatch) -> None:
    monkeypatch.setattr(keyboard_state.sys, "platform", "win32")

    assert keyboard_state.windows_key_is_pressed("f13") is None
