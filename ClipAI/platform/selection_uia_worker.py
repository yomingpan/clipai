"""Private, content-in-memory UIA worker. Never logs selection text."""
from __future__ import annotations

from dataclasses import asdict
import json
import sys
from io import TextIOWrapper
from typing import cast

from ClipAI.core.models import ExternalWindowRef, SelectionCaptureOutcome, SelectionSource
from ClipAI.platform.selection_uia import capture_windows_source


def _unknown(reason: str, *, detected: bool = False) -> SelectionCaptureOutcome:
    return SelectionCaptureOutcome(reason=reason, strategy="uia", selection_detected=detected)


def read_selection(source: SelectionSource) -> SelectionCaptureOutcome:
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
        focus_id = tuple(focused.GetRuntimeId())
        # Require the focused element's ancestry to contain this exact top-level HWND.
        path = []
        element = focused
        expected_hwnd = int(source.window.window_token.removeprefix("hwnd:"), 16)
        for _ in range(32):
            if element is None:
                return _unknown("uia_source_mismatch")
            path.append(element)
            if int(element.Current.NativeWindowHandle) == expected_hwnd:
                break
            element = TreeWalker.RawViewWalker.GetParent(element)
        else:
            return _unknown("uia_source_mismatch")

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
                outcome = SelectionCaptureOutcome(status="none", reason="uia_caret_only", strategy="uia")
                break
            try:
                # UIA RichEdit uses CR paragraph separators; preserve logical lines
                # as LF without trimming indentation or trailing selected whitespace.
                parts = [str(r.GetText(-1)).replace("\r\n", "\n").replace("\r", "\n") for r in selected]
            except Exception:
                outcome = _unknown("uia_text_failed", detected=True)
                break
            if any(not part for part in parts):
                outcome = _unknown("uia_selected_text_unavailable", detected=True)
            else:
                outcome = SelectionCaptureOutcome(
                    "\n".join(parts), "selected", strategy="uia", selection_detected=True,
                )
            break
        # An HWND may stay constant while focus moves between virtual controls.
        current = AutomationElement.FocusedElement
        if current is None or tuple(current.GetRuntimeId()) != focus_id:
            return _unknown("uia_focus_changed")
        if outcome.status in {"selected", "none"}:
            final_ranges = pattern.GetSelection()
            if final_ranges is None or len(final_ranges) != len(original_ranges) or not all(
                before.Compare(after) for before, after in zip(original_ranges, final_ranges)
            ):
                return _unknown("uia_selection_changed")
        if capture_windows_source(source.window) != source:
            return _unknown("source_changed")
        return outcome
    except Exception:
        return _unknown("uia_provider_failed")


def main() -> None:
    cast(TextIOWrapper, sys.stdin).reconfigure(encoding="utf-8")
    cast(TextIOWrapper, sys.stdout).reconfigure(encoding="utf-8")
    try:
        payload = json.loads(sys.stdin.read())
        source = SelectionSource(
            ExternalWindowRef(payload["window_token"], payload["process_id"], payload["observation_sequence"]),
            payload["focus_token"],
        )
        outcome = read_selection(source)
    except Exception:
        outcome = _unknown("uia_invalid_request")
    sys.stdout.write(json.dumps(asdict(outcome), ensure_ascii=True))


if __name__ == "__main__":
    main()
