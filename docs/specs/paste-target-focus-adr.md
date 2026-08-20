# ADR: Result paste target and Popup focus

## Context

The result Popup can remain visible while another Windows application owns
keyboard focus. In that state, native `Ctrl+V` pastes the original clipboard
content, while the same shortcut in a focused Popup requests a temporary
text-paste transaction. Visibility therefore cannot identify either keyboard
focus or the destination of the paste side effect.

## Decision

- Keep `Ctrl+V` as the familiar external result-paste gesture on every focused
  Voice Draft surface, including Editing mode. `Ctrl+Enter` still toggles
  Editing and Reading presentation, but never changes the `Ctrl+V` intent.
  The explicit Paste button remains available in both modes for sending a
  reviewed draft to its external target.
- After an unpinned Voice Draft is `dispatched_unconfirmed`, close that Voice
  Workflow through the normal close command. Other unpinned result Workflows
  retain their existing hidden-but-available behavior.
- Track the latest non-ClipAI Windows foreground window as an immutable,
  in-memory paste target.
- Let `PasteTargetCoordinator` own the latest target; the Windows adapter only
  observes, validates, activates, and sends keyboard input.
- Capture the target when `PasteResult` begins. A later foreground observation
  cannot redirect that operation.
- A Voice Draft freezes the target observed when capture starts when one is
  available. A targetless Voice Draft remains valid and uses the latest target
  only when `PasteResult` begins.
- Show focus and destination with both a persistent label and border state.
- Establish initial interactive Popup focus only after layout and native window
  activation have completed. All shortcut-created result Popups, including
  Voice Listening and Finalizing, request foreground activation immediately.
  Report `FocusEntered` only when both native activation and toolkit focus are
  confirmed; a failed focus request is not focus truth.
- Treat native outside-pointer presses as an independent Popup lifecycle fact.
  A visible unpinned Popup closes on the first outside press even when Windows
  denied its initial foreground request. The same transition owner retains the
  pin, owned-dialog, and active-Paste guards.
- Reject an unavailable target and focus the Popup with a visible error. Never
  fall back to whichever window happens to be foreground.
- Keep window titles out of persistence, logs, and diagnostics.

### Terminal outcome and Popup behavior

| Paste terminal outcome | Popup behavior | Focus behavior |
| --- | --- | --- |
| `failed` before dispatch | restore the Popup and show failure | activate the Popup |
| `cancelled` | restore the Popup without claiming failure | do not steal focus |
| `dispatched_unconfirmed`, unpinned | keep the Popup hidden and release semantic foreground | do not steal focus |
| `dispatched_unconfirmed`, pinned | keep the Popup visible and show the warning | do not steal focus |
| `cleanup_failed` | restore the Popup and show the cleanup warning | do not steal focus |

There is no Paste `succeeded` state. Returning from keyboard injection proves
dispatch only, so the UI must ask the user to confirm the target before retrying.
An older operation acknowledgement cannot restore, hide, or focus the current
Paste transition.

Hiding an unpinned Popup after `dispatched_unconfirmed` does not delete a
general result Workflow. `AppRuntime` releases semantic Foreground Workflow so
later global input is not routed to a hidden surface. For a Voice Draft only,
the same authoritative terminal completion instead routes through the normal
close command after clipboard cleanup settles. This disposes the Voice Popup so
the next global Voice shortcut starts a fresh Workflow rather than being
blocked by a hidden Voice Popup. Cleanup failure keeps the dispatch fact visible
because an automatic retry could duplicate content.

`PopupExternalOutputTransitions` owns the Popup's local transition table for
copy, archive, speech, and Paste acknowledgements. Its small interface accepts
operation begin, acknowledgement, and toolkit focus facts, then returns explicit
UI actions. It owns stale acknowledgement rejection, Paste pin capture,
hide/restore/no-activate decisions, whether Paste still owns a withdrawal, and
focus-check generations. Attention received before Paste settles is deferred
until its ordered terminal acknowledgement so it cannot steal the external
target before dispatch. The runtime then closes an unpinned dispatched Voice
Workflow, while other unpinned Workflows remain hidden and pinned Workflows
remain available for later attention. Only an observed focus entry or an
explicit Paste restoration releases that local withdrawal fact, and snapshot
revisions do not imply visibility. BaseDialog and the presenter execute those
actions without duplicating their policy.

Voice Draft rendering separately preserves the current insertion caret when an
authoritative content revision replaces widget text. Toolkit text marks remain
presentation state and do not create a second Workflow or Voice Draft owner.

## Alternatives

A new shortcut would reduce focus ambiguity but add learning cost. A
confirmation step would be safest but adds friction to every paste. Both remain
review options if observed paste-target failures remain common.

## Consequences and review trigger

The runtime gains a focused foreground observation seam and targeted keyboard
port, while semantic Foreground Workflow ownership remains unchanged. The
Popup transition table is local and replaceable without changing runtime
semantics. Review this decision if another Popup output mechanism needs a second
identity, visibility, or focus policy; if target activation failures are common
in Windows smoke tests; or before supporting paste destinations on another
operating system.
