# ADR-0014: Source-bound selection evidence

Status: accepted, 2026-09-05.

## Context

The 20260905-145021 diagnostics show alternating selection availability in the same foreground window. Failed attempts take approximately the compatibility-copy timeout. A timeout used to return `empty`, and `SelectionReader.read_text` erased every non-text outcome. Neither a successful foreground check nor an unchanged clipboard proves the absence of a selection.

## Decision

Retain the existing input, Workflow, and clipboard owners. Replace the string-only selection port with a typed capture request and `selected`, `none`, `unknown`, or `cancelled` outcome. Bind HWND/PID and native focus before Entry Panel or Workflow projection; validate them again during capture. Read UIA TextPattern selection first in a disposable, hidden worker with a two-second deadline and cancellation. Validate UIA focus, ancestry, and unchanged selection ranges before accepting its answer.

Only a supported source reporting degenerate caret ranges proves `none`. Unsupported providers, missing ranges, failure, timeout, source changes, and cancellation do not. The existing Ctrl+C transaction is allowed only when the probe has positive evidence of a selection but cannot read its text. It remains subject to modifier release, source checks, and conditional clipboard restoration. Its timeout is always `unknown`.

Entry Panel captures clipboard fallback facts once, exposes unknown state truthfully, and supports a typed `UseEntryPanelClipboard` intent to choose those frozen facts explicitly. Direct Actions, contextual questions, and speech use the same typed selection policy. Explicit clipboard-only modes remain explicit clipboard requests.

## Alternatives

Longer Ctrl+C delays and unconditional retries do not establish selection absence. A full rewrite would not remove external application limitations. Screen OCR does not preserve the complete underlying selection and is outside this change.

## Consequences

Supported controls no longer require a clipboard mutation or Alt release to read selection. Unknown states may be more visible in unsupported applications; this prevents accidental use of old text. UIA startup adds latency, bounded independently of the UI thread. Logical line endings are normalized to LF; indentation and trailing selected whitespace are preserved. Multiple disjoint ranges are joined in provider order with LF separators.

Windows venv executables may redirect to another process. The helper launches the base interpreter with the current import paths so its tracked PID is the actual UIA worker and can be killed/reaped on timeout. No source text is logged or passed on the command line.

## Review trigger

Add an application-specific probe behind the same port only after recording that application's unsupported or inconsistent TextPattern behavior. Revisit on any wrong-source input, automatic fallback from unknown, worker leak, or recurring latency problem. Do not infer universal application reliability from simulated tests or the owned RichTextBox smoke test.
