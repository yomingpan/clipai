from __future__ import annotations

import shutil
import subprocess
import sys

import pytest

from ClipAI.platform.clipboard import SystemClipboard, _is_hglobal_clipboard_format


@pytest.mark.parametrize("format_id", [1, 4, 5, 6, 7, 8, 10, 11, 12, 13, 15, 16, 17, 0x0081])
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
        0x0300,  # CF_GDIOBJFIRST
        0xC000,  # registered format with application-defined handle semantics
    ],
)
def test_opaque_handle_formats_are_not_treated_as_global_memory(format_id: int) -> None:
    assert _is_hglobal_clipboard_format(format_id) is False


@pytest.mark.integration
@pytest.mark.skipif(sys.platform != "win32", reason="uses the real Windows clipboard")
def test_snapshot_does_not_treat_bitmap_handle_as_global_memory() -> None:
    clipboard = SystemClipboard()
    original = clipboard.snapshot()
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
