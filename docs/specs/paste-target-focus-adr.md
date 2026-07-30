# ADR: Result paste target and Popup focus

## Context

The result Popup can remain visible while another Windows application owns
keyboard focus. In that state, native `Ctrl+V` pastes the original clipboard
content, while the same shortcut in a focused Popup requests a temporary
text-paste transaction. Visibility therefore cannot identify either keyboard
focus or the destination of the paste side effect.

## Decision

- Keep `Ctrl+V` as the familiar user gesture.
- Track the latest non-ClipAI Windows foreground window as an immutable,
  in-memory paste target.
- Let `PasteTargetCoordinator` own the latest target; the Windows adapter only
  observes, validates, activates, and sends keyboard input.
- Capture the target when `PasteResult` begins. A later foreground observation
  cannot redirect that operation.
- Show focus and destination with both a persistent label and border state.
- Reject an unavailable target and focus the Popup with a visible error. Never
  fall back to whichever window happens to be foreground.
- Keep window titles out of persistence, logs, and diagnostics.

## Alternatives

A new shortcut would reduce focus ambiguity but add learning cost. A
confirmation step would be safest but adds friction to every paste. Both remain
review options if observed paste-target failures remain common.

## Consequences and review trigger

The runtime gains a focused foreground observation seam and targeted keyboard
port, while semantic Foreground Workflow ownership remains unchanged. Review
this decision if target activation failures are common in Windows smoke tests,
or before supporting paste destinations on another operating system.
