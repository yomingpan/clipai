from __future__ import annotations

from io import BytesIO
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import time

import pyperclip

from ClipAI.core.errors import InputError
from ClipAI.core.models import ImageContent

MAX_CLIPBOARD_IMAGE_BYTES = 20 * 1024 * 1024


@dataclass(frozen=True)
class _ClipboardFormatSnapshot:
    format_id: int
    data: bytes


@dataclass(frozen=True)
class WindowsClipboardSnapshot:
    formats: tuple[_ClipboardFormatSnapshot, ...]


class SystemClipboard:
    def snapshot(self) -> WindowsClipboardSnapshot:
        return _snapshot_native_formats()

    def sequence_number(self) -> int:
        return int(ctypes.windll.user32.GetClipboardSequenceNumber())

    def restore_if_unchanged(self, snapshot: WindowsClipboardSnapshot, expected_sequence: int) -> bool:
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


def _snapshot_native_formats() -> WindowsClipboardSnapshot:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    _configure_clipboard_functions(user32, kernel32)
    _open_clipboard(user32)
    formats: list[_ClipboardFormatSnapshot] = []
    try:
        format_id = 0
        while True:
            format_id = int(user32.EnumClipboardFormats(format_id))
            if format_id == 0:
                break
            handle = user32.GetClipboardData(format_id)
            if not handle:
                continue
            size = int(kernel32.GlobalSize(handle))
            if size <= 0:
                continue
            pointer = kernel32.GlobalLock(handle)
            if not pointer:
                continue
            try:
                formats.append(_ClipboardFormatSnapshot(format_id, ctypes.string_at(pointer, size)))
            finally:
                kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()
    return WindowsClipboardSnapshot(tuple(formats))


def _replace_clipboard(snapshot: WindowsClipboardSnapshot) -> None:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    _configure_clipboard_functions(user32, kernel32)
    handles = [
        (item.format_id, _global_memory(item.data, kernel32))
        for item in snapshot.formats
    ]
    _open_clipboard(user32)
    transferred: set[int] = set()
    try:
        if not user32.EmptyClipboard():
            raise ctypes.WinError()
        for clipboard_format, handle in handles:
            if not user32.SetClipboardData(clipboard_format, handle):
                raise ctypes.WinError()
            transferred.add(handle)
    finally:
        user32.CloseClipboard()
        for _format, handle in handles:
            if handle not in transferred:
                kernel32.GlobalFree(handle)


def _configure_clipboard_functions(user32, kernel32) -> None:
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
    kernel32.GlobalSize.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalSize.restype = ctypes.c_size_t
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    user32.EnumClipboardFormats.argtypes = [wintypes.UINT]
    user32.EnumClipboardFormats.restype = wintypes.UINT


def _open_clipboard(user32) -> None:
    for attempt in range(10):
        if user32.OpenClipboard(None):
            return
        if attempt == 9:
            raise OSError("Clipboard is busy")
        time.sleep(0.01)


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
