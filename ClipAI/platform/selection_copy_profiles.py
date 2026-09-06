"""Verified selection-only Copy sources; never a blanket unknown-source fallback."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AccessibleControlIdentity:
    class_name: str
    framework: str


def supports_selection_only_copy(
    process_name: str, ancestry: tuple[AccessibleControlIdentity, ...],
) -> bool:
    """Anki's main card view routes Ctrl+C to QWebEnginePage.WebAction.Copy.

    Require the actual process and the focused control's validated ancestry.
    Toolbars, editors, arbitrary Qt windows and sibling WebViews are excluded.
    The caller must independently validate HWND/PID, focus and password state.
    """
    return (
        process_name.casefold() == "anki"
        and bool(ancestry)
        and ancestry[-1] == AccessibleControlIdentity("AnkiQt", "Qt")
        and AccessibleControlIdentity("MainWebView", "Qt") in ancestry[:-1]
        and all(control.framework == "Qt" for control in ancestry)
    )
