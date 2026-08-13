# ADR-0007: Popup focus requires native and toolkit evidence

## Status

Accepted.

## Context

Tk can emit `<FocusIn>` after Windows rejects a foreground request. The former
zero-field `FocusEntered()` let any caller claim focus without saying what was
observed. Alt+Tab, a taskbar switch, or another application taking foreground
also need not produce Tk `<FocusOut>` or an outside pointer press, so Popup
focus could remain projected after native ownership was lost.

## Decision

`FocusEntered` carries two mandatory, named facts: `native_foreground` and
`toolkit_focused`. Only their conjunction is confirmed. An unconfirmed entry
projects unfocused before initial focus is established and cannot replace an
already confirmed focus.

`ForegroundLeftApplication(pinned)` is an independent fact handled by
`PopupExternalOutputTransitions`, the existing transition owner. It releases
the control surface and closes an unpinned Popup. Active Paste and owned dialogs
suppress it because those flows intentionally yield foreground.

The presenter observes toolkit focus with `focus_get`, native ownership through
`NativeWindowSurface`, and polls native ownership on the existing 25 ms UI tick
only while a Popup is confirmed focused. `apply_external_output_visibility()`
returns a boolean and callers handle failure. A
`logging.diagnostics.focus_transitions` switch records native evidence,
toolkit evidence, and the projected value together.

## Measurements

Before the change, the Q3 AST loop found seven evidence-free
`FocusEntered()` construction sites and one discarded visibility result. The
focused architecture/UI/config/container suite now reports 221 passing tests in
10.25 s. The runtime observation interval is 25 ms, matching the existing UI
command tick; manual Windows scenarios are specified in the release checklist.

## Rejected alternatives

- Trusting Tk `<FocusIn>` alone preserves the original false-positive state.
- Trusting native foreground alone loses which toolkit surface owns focus.
- Adding default values to `FocusEntered` lets callers continue asserting facts
  they did not verify.
- Depending on `<FocusOut>` or outside clicks misses documented Windows task
  switching paths.
- Letting widgets construct `SetFocusProjection` creates a second transition
  owner and bypasses Paste/owned-dialog guards.

## Consequences

- `focused_inside` means confirmed native and toolkit focus, not a toolkit hint.
- Alt+Tab and external foreground theft are observable without a global event
  bus.
- Paste and owned-dialog focus handoffs remain explicit exceptions in one owner.
- Diagnostics can compare all three values without changing product policy.
