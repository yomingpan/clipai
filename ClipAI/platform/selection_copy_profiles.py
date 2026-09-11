"""Verified selection-only Copy sources; never a blanket unknown-source fallback."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PureWindowsPath
import re


@dataclass(frozen=True)
class AccessibleControlIdentity:
    class_name: str
    framework: str


@dataclass(frozen=True)
class FocusRepairPlan:
    """Platform-only instructions for a bounded in-window focus repair."""

    target: AccessibleControlIdentity
    focus_first_child: bool = False


@dataclass(frozen=True)
class SelectionSourcePolicy:
    """Capabilities established by one source profile evaluation."""

    copy_selection_only: bool = False
    focus_repair: FocusRepairPlan | None = None


_ANKI_ROOT = AccessibleControlIdentity("AnkiQt", "Qt")
_ANKI_CARD = AccessibleControlIdentity("MainWebView", "Qt")
_ANKI_REPAIRABLE_SHELL_CONTROLS = frozenset(
    {
        AccessibleControlIdentity("AnkiQt", "Qt"),
        AccessibleControlIdentity("QWidget", "Qt"),
        AccessibleControlIdentity("QObject", "Qt"),
    }
)


def selection_source_policy(
    process_name: str,
    executable_path: str,
    ancestry: tuple[AccessibleControlIdentity, ...],
) -> SelectionSourcePolicy:
    """Evaluate verified capabilities without leaking app identity to callers.

    Anki is currently the only evidenced profile. Its card routes Ctrl+C to a
    selection-only action. Focus repair is admitted only from its inert Qt shell;
    menus, editors, toolbars, sibling WebViews and arbitrary controls fail closed.
    """
    if (
        not _is_verified_anki_process(process_name, executable_path)
        or not ancestry
        or ancestry[-1] != _ANKI_ROOT
        or any(control.framework != "Qt" for control in ancestry)
    ):
        return SelectionSourcePolicy()
    if _ANKI_CARD in ancestry[:-1]:
        return SelectionSourcePolicy(copy_selection_only=True)
    if all(control in _ANKI_REPAIRABLE_SHELL_CONTROLS for control in ancestry):
        return SelectionSourcePolicy(
            focus_repair=FocusRepairPlan(_ANKI_CARD, focus_first_child=True)
        )
    return SelectionSourcePolicy()


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
