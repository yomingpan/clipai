import ctypes
from types import SimpleNamespace

import pytest

from ClipAI.platform import keyboard_menu


@pytest.mark.parametrize("accepted", [0, 1, 2])
def test_menu_mask_sends_only_balanced_unassigned_key_and_checks_native_result(monkeypatch, accepted):
    calls = []
    class SendInput:
        def __call__(self, count, inputs, size):
            values = ctypes.cast(inputs, ctypes.POINTER(keyboard_menu._Input))
            calls.append((size, [(values[i].type, values[i].value.ki.wVk,
                                values[i].value.ki.dwFlags) for i in range(count)]))
            return accepted if len(calls) == 1 else 1
    sender = SendInput()
    libraries = []
    def load(name, **kwargs):
        libraries.append((name, kwargs))
        return SimpleNamespace(SendInput=sender)
    monkeypatch.setattr(ctypes, "WinDLL", load, raising=False)
    if accepted == 2:
        keyboard_menu.mask_alt_menu()
    else:
        with pytest.raises(OSError, match="rejected"):
            keyboard_menu.mask_alt_menu()
    assert calls[0] == (ctypes.sizeof(keyboard_menu._Input), [(1, 0xE8, 0), (1, 0xE8, 2)])
    assert len(calls) == (2 if accepted == 1 else 1)
    if accepted == 1:
        assert calls[1][1] == [(1, 0xE8, 2)]
    assert sender.argtypes == (ctypes.wintypes.UINT, ctypes.POINTER(keyboard_menu._Input), ctypes.c_int)
    assert sender.restype == ctypes.wintypes.UINT
    assert libraries == [("user32", {"use_last_error": True})]
