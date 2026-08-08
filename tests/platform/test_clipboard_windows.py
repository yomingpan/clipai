from __future__ import annotations

import shutil
import subprocess
import sys
import ctypes

import pytest

import ClipAI.platform.clipboard as clipboard_module
from ClipAI.core.errors import InputError
from ClipAI.platform.clipboard import SystemClipboard, WindowsClipboardSnapshot, _ClipboardFormatSnapshot, _is_hglobal_clipboard_format, _is_redundant_opaque_format, _replace_clipboard, _transient_text_snapshot


@pytest.mark.parametrize(
    "format_id",
    [1, 4, 5, 6, 7, 8, 10, 11, 12, 13, 15, 16, 17, 0x0081, 0x0300, 0x03FF, 0xC000, 0xFFFF],
)
def test_documented_global_memory_formats_are_snapshot_safe(format_id: int) -> None:
    assert _is_hglobal_clipboard_format(format_id) is True


@pytest.mark.parametrize(
    "format_id",
    [
        2,  # CF_BITMAP (HBITMAP)
        3,  # CF_METAFILEPICT (contains an HMETAFILE)
        9,  # CF_PALETTE (HPALETTE)
        14,  # CF_ENHMETAFILE (HENHMETAFILE)
        0x0080,  # CF_OWNERDISPLAY
        0x0082,  # CF_DSPBITMAP
        0x0083,  # CF_DSPMETAFILEPICT
        0x008E,  # CF_DSPENHMETAFILE
        0x0200,  # CF_PRIVATEFIRST
    ],
)
def test_opaque_handle_formats_are_not_treated_as_global_memory(format_id: int) -> None:
    assert _is_hglobal_clipboard_format(format_id) is False


def test_bitmap_and_palette_are_skipped_only_when_lossless_dib_is_available() -> None:
    assert _is_redundant_opaque_format(2, frozenset({2, 8})) is True
    assert _is_redundant_opaque_format(9, frozenset({9, 17})) is True
    assert _is_redundant_opaque_format(2, frozenset({2})) is False


def test_transient_text_excludes_history_monitoring_and_cloud_sync() -> None:
    registered: list[str] = []

    def register(name: str) -> int:
        registered.append(name)
        return 0xC000 + len(registered)

    snapshot = _transient_text_snapshot("result", register)

    assert snapshot.formats[0].format_id == 13
    assert snapshot.formats[0].data.decode("utf-16-le").rstrip("\x00") == "result"
    assert registered == [
        "HTML Format",
        "ExcludeClipboardContentFromMonitorProcessing",
        "CanIncludeInClipboardHistory",
        "CanUploadToCloudClipboard",
    ]
    assert [item.data for item in snapshot.formats[2:]] == [b"\x00\x00\x00\x00"] * 3


def test_transient_text_adds_safe_html_with_explicit_line_breaks() -> None:
    ids = iter((0xC100, 0xC101, 0xC102, 0xC103))
    snapshot = _transient_text_snapshot("第一行 <範圍>\n第二行 & final", lambda _name: next(ids))

    html_payload = snapshot.formats[1].data.rstrip(b"\x00")
    header, html = html_payload.split(b"<html>", 1)
    complete_html = b"<html>" + html
    offsets = {
        line.split(b":", 1)[0].decode("ascii"): int(line.split(b":", 1)[1])
        for line in header.splitlines()
        if line.startswith((b"Start", b"End"))
    }

    expected_fragment = "第一行 &lt;範圍&gt;<br>第二行 &amp; final".encode("utf-8")
    assert expected_fragment in complete_html
    assert html_payload[offsets["StartHTML"] : offsets["EndHTML"]] == complete_html
    assert html_payload[offsets["StartFragment"] : offsets["EndFragment"]] == expected_fragment


def test_explicit_copy_uses_public_plain_and_html_snapshot(monkeypatch) -> None:
    expected = WindowsClipboardSnapshot((_ClipboardFormatSnapshot(13, b"payload"),))
    calls: list[tuple[str, bool]] = []
    replacements: list[WindowsClipboardSnapshot] = []

    def snapshot(text: str, *, private: bool) -> WindowsClipboardSnapshot:
        calls.append((text, private))
        return expected

    monkeypatch.setattr(clipboard_module, "_text_snapshot", snapshot)
    monkeypatch.setattr(clipboard_module, "_replace_clipboard", replacements.append)

    SystemClipboard().write_text("first\nsecond")

    assert calls == [("first\nsecond", False)]
    assert replacements == [expected]


def test_transient_text_uses_windows_line_endings() -> None:
    snapshot = _transient_text_snapshot(
        "first\nsecond\rthird\r\nfourth",
        lambda _name: 0xC001,
    )

    assert snapshot.formats[0].data.decode("utf-16-le").rstrip("\x00") == (
        "first\r\nsecond\r\nthird\r\nfourth"
    )


@pytest.mark.integration
@pytest.mark.skipif(sys.platform != "win32", reason="uses the real Windows clipboard")
def test_explicit_copy_registers_plain_text_and_html() -> None:
    clipboard = SystemClipboard()
    try:
        original = clipboard.snapshot()
    except InputError as exc:
        pytest.skip(f"current clipboard cannot be safely preserved: {exc}")
    user32 = ctypes.windll.user32
    try:
        clipboard.write_text("第一行\n第二行")
        assert clipboard.read_text().splitlines() == ["第一行", "第二行"]
        assert user32.IsClipboardFormatAvailable(int(user32.RegisterClipboardFormatW("HTML Format")))
    finally:
        owned_sequence = clipboard.sequence_number()
        clipboard.restore_if_unchanged(original, owned_sequence)


@pytest.mark.integration
@pytest.mark.skipif(sys.platform != "win32", reason="uses the real Windows clipboard")
def test_registered_rich_text_survives_transient_paste_transaction() -> None:
    clipboard = SystemClipboard()
    try:
        original = clipboard.snapshot()
    except InputError as exc:
        pytest.skip(f"current clipboard cannot be safely preserved: {exc}")
    user32 = ctypes.windll.user32
    rtf_format = int(user32.RegisterClipboardFormatW("Rich Text Format"))
    rich_text = b"{\\rtf1\\ansi preserved}"
    test_snapshot = WindowsClipboardSnapshot((
        _ClipboardFormatSnapshot(rtf_format, rich_text),
        _ClipboardFormatSnapshot(13, "preserved".encode("utf-16-le") + b"\x00\x00"),
    ))
    try:
        assert _replace_clipboard(test_snapshot) is True
        captured = clipboard.snapshot()
        assert any(item.format_id == rtf_format and item.data == rich_text for item in captured.formats)
        clipboard.write_transient_text("temporary")
        owned_sequence = clipboard.sequence_number()
        assert clipboard.restore_if_unchanged(captured, owned_sequence) is True
        restored = clipboard.snapshot()
        assert any(item.format_id == rtf_format and item.data == rich_text for item in restored.formats)
    finally:
        owned_sequence = clipboard.sequence_number()
        clipboard.restore_if_unchanged(original, owned_sequence)


@pytest.mark.integration
@pytest.mark.skipif(sys.platform != "win32", reason="uses the real Windows clipboard")
def test_transient_text_registers_windows_privacy_formats() -> None:
    clipboard = SystemClipboard()
    try:
        original = clipboard.snapshot()
    except InputError as exc:
        pytest.skip(f"current clipboard cannot be safely preserved: {exc}")
    user32 = ctypes.windll.user32
    try:
        clipboard.write_transient_text("temporary")
        assert user32.IsClipboardFormatAvailable(int(user32.RegisterClipboardFormatW("HTML Format")))
        for name in (
            "ExcludeClipboardContentFromMonitorProcessing",
            "CanIncludeInClipboardHistory",
            "CanUploadToCloudClipboard",
        ):
            format_id = int(user32.RegisterClipboardFormatW(name))
            assert user32.IsClipboardFormatAvailable(format_id)
    finally:
        owned_sequence = clipboard.sequence_number()
        clipboard.restore_if_unchanged(original, owned_sequence)


@pytest.mark.integration
@pytest.mark.skipif(sys.platform != "win32", reason="uses the real Windows clipboard")
def test_snapshot_does_not_treat_bitmap_handle_as_global_memory() -> None:
    clipboard = SystemClipboard()
    try:
        original = clipboard.snapshot()
    except InputError as exc:
        pytest.skip(f"current clipboard cannot be safely preserved: {exc}")
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    assert powershell is not None
    try:
        setup = subprocess.run(
            [
                powershell,
                "-NoProfile",
                "-STA",
                "-Command",
                "Add-Type -AssemblyName System.Windows.Forms; "
                "Add-Type -AssemblyName System.Drawing; "
                "$bitmap = New-Object System.Drawing.Bitmap 2,2; "
                "[System.Windows.Forms.Clipboard]::SetImage($bitmap); "
                "$bitmap.Dispose()",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert setup.returncode == 0, (setup.stdout, setup.stderr)

        script = (
            "from ClipAI.platform.clipboard import SystemClipboard; "
            "clipboard = SystemClipboard(); "
            "snapshot = clipboard.snapshot(); "
            "assert all(item.format_id != 2 for item in snapshot.formats); "
            "clipboard.write_text('temporary'); "
            "owned_sequence = clipboard.sequence_number(); "
            "assert clipboard.restore_if_unchanged(snapshot, owned_sequence); "
            "assert clipboard.read_image() is not None; "
            "print('snapshot-safe', flush=True)"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
        assert result.stdout.strip() == "snapshot-safe"
    finally:
        clipboard.write_text("__CLIPAI_TEST_RESTORE__")
        owned_sequence = clipboard.sequence_number()
        clipboard.restore_if_unchanged(original, owned_sequence)
