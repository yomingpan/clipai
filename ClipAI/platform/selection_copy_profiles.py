"""Verified selection-only Copy sources; never a blanket unknown-source fallback."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PureWindowsPath
import re


@dataclass(frozen=True)
class AccessibleControlIdentity:
    class_name: str
    framework: str


def supports_selection_only_copy(
    process_name: str,
    executable_path: str,
    ancestry: tuple[AccessibleControlIdentity, ...],
) -> bool:
    """Anki's main card view routes Ctrl+C to QWebEnginePage.WebAction.Copy.

    Require the actual process and the focused control's validated ancestry.
    Toolbars, editors, arbitrary Qt windows and sibling WebViews are excluded.
    The caller must independently validate HWND/PID, focus and password state.
    """
    return (
        _is_verified_anki_process(process_name, executable_path)
        and bool(ancestry)
        and ancestry[-1] == AccessibleControlIdentity("AnkiQt", "Qt")
        and AccessibleControlIdentity("MainWebView", "Qt") in ancestry[:-1]
        and all(control.framework == "Qt" for control in ancestry)
    )


def supports_card_focus_restore(
    process_name: str,
    executable_path: str,
    ancestry: tuple[AccessibleControlIdentity, ...],
) -> bool:
    """Authorize only an in-window focus repair for a verified Anki shell."""
    return (
        _is_verified_anki_process(process_name, executable_path)
        and bool(ancestry)
        and ancestry[-1] == AccessibleControlIdentity("AnkiQt", "Qt")
        and all(control.framework == "Qt" for control in ancestry)
    )


def _is_verified_anki_process(process_name: str, executable_path: str) -> bool:
    parts = tuple(part.casefold() for part in PureWindowsPath(executable_path).parts)
    if process_name.casefold() == "anki":
        return bool(parts) and parts[-1] == "anki.exe"
    if process_name.casefold() != "pythonw" or len(parts) < 4:
        return False
    runtime = parts[-2]
    return (
        parts[-1] == "pythonw.exe"
        and parts[-4] == "ankiprogramfiles"
        and parts[-3] == "python"
        and re.fullmatch(
            r"cpython-\d+(?:\.\d+){1,2}-windows-x86_64-none",
            runtime,
        ) is not None
    )
