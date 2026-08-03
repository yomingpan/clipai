from __future__ import annotations

from collections.abc import Callable
from io import BytesIO
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import struct
import time

import pyperclip

from ClipAI.core.errors import InputError
from ClipAI.core.models import ImageContent

MAX_CLIPBOARD_IMAGE_BYTES = 20 * 1024 * 1024

# GetClipboardData does not always return an HGLOBAL. Bitmap, palette,
# metafile, owner-display, and private formats can expose opaque native handles.
# The standard formats below, registered formats, and the CF_GDIOBJ range are
# documented as global-memory backed. CF_DIB and CF_DIBV5 preserve image
# content without copying a redundant synthesized CF_BITMAP handle.
_HGLOBAL_CLIPBOARD_FORMATS = frozenset({
    1,   # CF_TEXT
    4,   # CF_SYLK
    5,   # CF_DIF
    6,   # CF_TIFF
    7,   # CF_OEMTEXT
    8,   # CF_DIB
    10,  # CF_PENDATA
    11,  # CF_RIFF
    12,  # CF_WAVE
    13,  # CF_UNICODETEXT
    15,  # CF_HDROP
    16,  # CF_LOCALE
    17,  # CF_DIBV5
    0x0081,  # CF_DSPTEXT
})


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
        return _replace_clipboard(snapshot, expected_sequence=expected_sequence)

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

    def write_transient_text(self, text: str) -> None:
        _replace_clipboard(_transient_text_snapshot(text))


def _snapshot_native_formats() -> WindowsClipboardSnapshot:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    _configure_clipboard_functions(user32, kernel32)
    _open_clipboard(user32)
    formats: list[_ClipboardFormatSnapshot] = []
    try:
        format_ids: list[int] = []
        format_id = 0
        while True:
            format_id = int(user32.EnumClipboardFormats(format_id))
            if format_id == 0:
                break
            format_ids.append(format_id)
        available = frozenset(format_ids)
        for format_id in format_ids:
            if _is_redundant_opaque_format(format_id, available):
                continue
            if not _is_hglobal_clipboard_format(format_id):
                raise InputError(
                    f"Clipboard format {format_id} cannot be completely preserved safely."
                )
            handle = user32.GetClipboardData(format_id)
            if not handle:
                raise InputError(f"Clipboard format {format_id} could not be rendered for preservation.")
            size = int(kernel32.GlobalSize(handle))
            if size <= 0:
                raise InputError(f"Clipboard format {format_id} has no preservable global-memory data.")
            pointer = kernel32.GlobalLock(handle)
            if not pointer:
                raise InputError(f"Clipboard format {format_id} could not be locked for preservation.")
            try:
                formats.append(_ClipboardFormatSnapshot(format_id, ctypes.string_at(pointer, size)))
            finally:
                kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()
    return WindowsClipboardSnapshot(tuple(formats))


def _is_hglobal_clipboard_format(format_id: int) -> bool:
    return (
        format_id in _HGLOBAL_CLIPBOARD_FORMATS
        or 0x0300 <= format_id <= 0x03FF
        or 0xC000 <= format_id <= 0xFFFF
    )


def _is_redundant_opaque_format(format_id: int, available: frozenset[int]) -> bool:
    has_dib = 8 in available or 17 in available
    return has_dib and format_id in {2, 9}


def _replace_clipboard(
    snapshot: WindowsClipboardSnapshot,
    *,
    expected_sequence: int | None = None,
) -> bool:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    _configure_clipboard_functions(user32, kernel32)
    _open_clipboard(user32)
    handles: list[tuple[int, int]] = []
    transferred: set[int] = set()
    try:
        if expected_sequence is not None and int(user32.GetClipboardSequenceNumber()) != expected_sequence:
            return False
        handles = [
            (item.format_id, _global_memory(item.data, kernel32))
            for item in snapshot.formats
        ]
        if not user32.EmptyClipboard():
            raise ctypes.WinError()
        for clipboard_format, handle in handles:
            if not user32.SetClipboardData(clipboard_format, handle):
                raise ctypes.WinError()
            transferred.add(handle)
        return True
    finally:
        user32.CloseClipboard()
        for _format, handle in handles:
            if handle not in transferred:
                kernel32.GlobalFree(handle)


def _transient_text_snapshot(
    text: str,
    register_format: Callable[[str], int] | None = None,
) -> WindowsClipboardSnapshot:
    if register_format is None:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        _configure_clipboard_functions(user32, kernel32)
        register_format = lambda name: int(user32.RegisterClipboardFormatW(name))
    privacy_formats = (
        "ExcludeClipboardContentFromMonitorProcessing",
        "CanIncludeInClipboardHistory",
        "CanUploadToCloudClipboard",
    )
    formats = [_ClipboardFormatSnapshot(13, text.encode("utf-16-le") + b"\x00\x00")]
    for name in privacy_formats:
        format_id = register_format(name)
        if not format_id:
            raise ctypes.WinError()
        formats.append(_ClipboardFormatSnapshot(format_id, struct.pack("<I", 0)))
    return WindowsClipboardSnapshot(tuple(formats))


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
    user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
    user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
    user32.RegisterClipboardFormatW.restype = wintypes.UINT


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
