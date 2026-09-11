"""Private, content-in-memory UIA worker. Never logs selection text."""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import json
import sys
import time
from io import TextIOWrapper
from typing import cast

from ClipAI.core.models import ExternalWindowRef, SelectionCaptureOutcome, SelectionSource
from ClipAI.platform.selection_uia import capture_windows_source
from ClipAI.platform.selection_copy_profiles import (
    AccessibleControlIdentity,
    supports_card_focus_restore,
    supports_selection_only_copy,
)


@dataclass(frozen=True)
class NativeSelectionResult:
    outcome: SelectionCaptureOutcome
    worker_reusable: bool = True


def _unknown(reason: str, *, detected: bool = False, reusable: bool = True) -> NativeSelectionResult:
    return NativeSelectionResult(
        SelectionCaptureOutcome(reason=reason, strategy="uia", selection_detected=detected),
        reusable,
    )


def _ancestry(focused, walker, expected_hwnd: int):
    path = []
    element = focused
    for _ in range(32):
        if element is None:
            return None
        path.append(element)
        if int(element.Current.NativeWindowHandle) == expected_hwnd:
            return path
        element = walker.GetParent(element)
    return None


def _identity(path) -> tuple[AccessibleControlIdentity, ...]:
    return tuple(
        AccessibleControlIdentity(str(node.Current.ClassName), str(node.Current.FrameworkId))
        for node in path
    )


def _process_identity(process_id: int) -> tuple[str, str]:
    from System.Diagnostics import Process

    process = Process.GetProcessById(process_id)
    try:
        return str(process.ProcessName), str(process.MainModule.FileName)
    finally:
        process.Dispose()


def _find_main_webview(root, walker):
    first_child = getattr(walker, "GetFirstChild", None)
    next_sibling = getattr(walker, "GetNextSibling", None)
    if not callable(first_child) or not callable(next_sibling):
        return None
    pending = [first_child(root)]
    visited = 0
    while pending and visited < 128:
        element = pending.pop()
        if element is None:
            continue
        visited += 1
        if (
            str(element.Current.ClassName) == "MainWebView"
            and str(element.Current.FrameworkId) == "Qt"
        ):
            return element
        sibling = next_sibling(element)
        child = first_child(element)
        if sibling is not None:
            pending.append(sibling)
        if child is not None:
            pending.append(child)
    return None


def _restore_card_focus(api, walker, root, expected_hwnd: int):
    webview = _find_main_webview(root, walker)
    if webview is None:
        return None
    first_child = getattr(walker, "GetFirstChild", None)
    target = first_child(webview) if callable(first_child) else None
    target = target or webview
    try:
        target.SetFocus()
    except Exception:
        return None
    deadline = time.monotonic() + 0.15
    while time.monotonic() < deadline:
        focused = api.FocusedElement
        path = _ancestry(focused, walker, expected_hwnd) if focused is not None else None
        if path is not None and AccessibleControlIdentity("MainWebView", "Qt") in _identity(path):
            return focused, path
        time.sleep(0.01)
    return None


def read_selection(source: SelectionSource) -> NativeSelectionResult:
    if capture_windows_source(source.window) != source:
        return _unknown("source_changed")
    try:
        import clr

        for assembly in ("UIAutomationClient", "UIAutomationTypes"):
            clr.AddReference(f"{assembly}, Version=4.0.0.0, Culture=neutral, PublicKeyToken=31bf3856ad364e35")
        from System.Windows.Automation import AutomationElement, TextPattern, TreeWalker
        from System.Windows.Automation.Text import TextPatternRangeEndpoint

        focused = AutomationElement.FocusedElement
        if focused is None or focused.Current.IsPassword:
            return _unknown("uia_protected_or_unavailable")
        # Require the focused element's ancestry to contain this exact top-level HWND.
        expected_hwnd = int(source.window.window_token.removeprefix("hwnd:"), 16)
        walker = TreeWalker.RawViewWalker
        path = _ancestry(focused, walker, expected_hwnd)
        if path is None:
            return _unknown("uia_source_mismatch")

        focus_restored = False
        process_name = executable_path = ""
        try:
            process_name, executable_path = _process_identity(source.window.process_id)
        except Exception:
            pass
        ancestry = _identity(path)
        if (
            AccessibleControlIdentity("MainWebView", "Qt") not in ancestry
            and supports_card_focus_restore(process_name, executable_path, ancestry)
        ):
            restored = _restore_card_focus(api=AutomationElement, walker=walker, root=path[-1], expected_hwnd=expected_hwnd)
            if restored is None:
                return _unknown("uia_focus_restore_failed", reusable=False)
            focused, path = restored
            focus_restored = True
            ancestry = _identity(path)

        focus_id = tuple(focused.GetRuntimeId())

        outcome = _unknown("uia_unsupported")
        for element in path:
            if element.Current.IsPassword:
                return _unknown("uia_protected_or_unavailable")
            if not bool(element.GetCurrentPropertyValue(AutomationElement.IsTextPatternAvailableProperty)):
                continue
            pattern = element.GetCurrentPattern(TextPattern.Pattern)
            if str(pattern.SupportedTextSelection) == "None":
                continue
            ranges = pattern.GetSelection()
            if ranges is None or len(ranges) == 0:
                # No ranges is not the documented insertion-point evidence of no selection.
                outcome = _unknown("uia_no_ranges")
                break
            original_ranges = [r.Clone() for r in ranges]
            selected = [r for r in ranges if r.CompareEndpoints(
                TextPatternRangeEndpoint.Start, r, TextPatternRangeEndpoint.End,
            ) != 0]
            if not selected:
                outcome = NativeSelectionResult(SelectionCaptureOutcome(status="none", reason="uia_caret_only", strategy="uia"))
                break
            try:
                # UIA RichEdit uses CR paragraph separators; preserve logical lines
                # as LF without trimming indentation or trailing selected whitespace.
                parts = [str(r.GetText(-1)).replace("\r\n", "\n").replace("\r", "\n") for r in selected]
            except Exception:
                outcome = _unknown("uia_text_failed", detected=True, reusable=False)
                break
            if any(not part for part in parts):
                outcome = _unknown("uia_selected_text_unavailable", detected=True)
            else:
                outcome = NativeSelectionResult(SelectionCaptureOutcome(
                    "\n".join(parts), "selected", strategy="uia", selection_detected=True,
                ))
            break
        if outcome.outcome.reason == "uia_unsupported":
            if supports_selection_only_copy(process_name, executable_path, ancestry):
                outcome = NativeSelectionResult(SelectionCaptureOutcome(
                    reason="selection_only_copy_available", strategy="uia",
                    copy_selection_only=True,
                ))
        # An HWND may stay constant while focus moves between virtual controls.
        current = AutomationElement.FocusedElement
        if current is None or tuple(current.GetRuntimeId()) != focus_id:
            return _unknown("uia_focus_changed")
        if outcome.outcome.status in {"selected", "none"}:
            final_ranges = pattern.GetSelection()
            if final_ranges is None or len(final_ranges) != len(original_ranges) or not all(
                before.Compare(after) for before, after in zip(original_ranges, final_ranges)
            ):
                return _unknown("uia_selection_changed")
        current_source = capture_windows_source(source.window)
        if (
            current_source is None
            or current_source.window.window_token != source.window.window_token
            or current_source.window.process_id != source.window.process_id
            or (not focus_restored and current_source != source)
        ):
            return _unknown("source_changed")
        return replace(outcome, outcome=replace(outcome.outcome, focus_restored=focus_restored))
    except Exception:
        return _unknown("uia_provider_failed", reusable=False)


def main() -> None:
    cast(TextIOWrapper, sys.stdin).reconfigure(encoding="utf-8")
    cast(TextIOWrapper, sys.stdout).reconfigure(encoding="utf-8")
    for line in sys.stdin:
        try:
            payload = json.loads(line)
            source = SelectionSource(
                ExternalWindowRef(payload["window_token"], payload["process_id"], payload["observation_sequence"]),
                payload["focus_token"],
            )
            outcome = read_selection(source)
        except Exception:
            outcome = _unknown("uia_invalid_request", reusable=False)
        sys.stdout.write(json.dumps(worker_response(outcome), ensure_ascii=True) + "\n")
        sys.stdout.flush()


def worker_response(result: NativeSelectionResult) -> dict[str, object]:
    """Native evidence owns reuse admission; diagnostics never drive transport."""
    return {**asdict(result.outcome), "worker_reusable": result.worker_reusable}


if __name__ == "__main__":
    main()
