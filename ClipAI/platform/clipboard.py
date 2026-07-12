from __future__ import annotations

from io import BytesIO
import ctypes
from ctypes import wintypes
import time

import pyperclip

from ClipAI.core.errors import InputError
from ClipAI.core.models import ClipboardSnapshot, ImageContent

MAX_CLIPBOARD_IMAGE_BYTES = 20 * 1024 * 1024


class SystemClipboard:
    def snapshot(self) -> ClipboardSnapshot:
        return ClipboardSnapshot(text=self.read_text(), image=self.read_image())

    def sequence_number(self) -> int:
        return int(ctypes.windll.user32.GetClipboardSequenceNumber())

    def restore_if_unchanged(self, snapshot: ClipboardSnapshot, expected_sequence: int) -> bool:
        if self.sequence_number() != expected_sequence:
            return False
        _replace_clipboard(snapshot)
        return True

    def read_image(self) -> ImageContent | None:
        try:
            from PIL import Image, ImageGrab

            value = ImageGrab.grabclipboard()
            if not isinstance(value, Image.Image):
                return None
            buffer = BytesIO()
            value.convert("RGB").save(buffer, format="PNG", optimize=True)
            data = buffer.getvalue()
        except (OSError, ValueError) as exc:
            raise InputError("Clipboard image could not be decoded.") from exc
        if len(data) > MAX_CLIPBOARD_IMAGE_BYTES:
            raise InputError("Clipboard image is too large. Copy a smaller image and try again.")
        return ImageContent(data=data, mime_type="image/png")

    def read_text(self) -> str:
        value = pyperclip.paste()
        return "" if value is None else str(value)

    def write_text(self, text: str) -> None:
        pyperclip.copy(text)


def _replace_clipboard(snapshot: ClipboardSnapshot) -> None:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.CloseClipboard.restype = wintypes.BOOL
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    cf_unicode_text = 13
    cf_dib = 8
    handles: list[tuple[int, int]] = []

    if snapshot.text:
        handles.append((cf_unicode_text, _global_memory(snapshot.text.encode("utf-16-le") + b"\x00\x00", kernel32)))
    if snapshot.image is not None:
        from PIL import Image

        with Image.open(BytesIO(snapshot.image.data)) as image:
            bitmap = BytesIO()
            image.convert("RGB").save(bitmap, format="BMP")
        handles.append((cf_dib, _global_memory(bitmap.getvalue()[14:], kernel32)))

    for attempt in range(10):
        if user32.OpenClipboard(None):
            break
        if attempt == 9:
            raise OSError("Clipboard is busy")
        time.sleep(0.01)
    try:
        if not user32.EmptyClipboard():
            raise ctypes.WinError()
        for clipboard_format, handle in handles:
            if not user32.SetClipboardData(clipboard_format, handle):
                raise ctypes.WinError()
    finally:
        user32.CloseClipboard()


def _global_memory(data: bytes, kernel32) -> int:
    gmem_moveable = 0x0002
    handle = kernel32.GlobalAlloc(gmem_moveable, len(data))
    if not handle:
        raise ctypes.WinError()
    pointer = kernel32.GlobalLock(handle)
    if not pointer:
        kernel32.GlobalFree(handle)
        raise ctypes.WinError()
    try:
        ctypes.memmove(pointer, data, len(data))
    finally:
        kernel32.GlobalUnlock(handle)
    return handle
