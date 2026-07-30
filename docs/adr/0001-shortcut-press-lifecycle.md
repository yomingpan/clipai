# ADR 0001: Shortcut Press Lifecycle

- Status: Accepted
- Date: 2026-07-30

## Context

The desktop listener previously assigned one gesture identity to every key
held in the same modifier context. The Shortcut Guide captured that identity
to prevent practice presses from executing Actions. If the guide closed while
Ctrl and Alt remained held, the next function-key press reused the captured
identity and was incorrectly quarantined.

Trigger and progress callbacks also represented overlapping lifecycle facts.
Release, cancellation, invalid attempts, and Escape interruption were encoded
as variants of one press-type field, leaving ownership and ordering ambiguous.

## Decision

The platform hotkey module is the single owner of physical key
classification, pressed-key reconciliation, long-press timers, stale recovery,
and `ShortcutPressId` creation.

Each complete binding match creates a distinct Shortcut Press. Its typed facts
are emitted through one ordered callback:

- `ShortcutPressStarted`
- `ShortcutPressInvoked` with `short` or `long`
- `ShortcutPressEnded` with `released` or `cancelled`
- `ShortcutAttemptRejected`
- `InterruptionRequested` with `current` or `all`

`ShortcutKeyStateChanged` is observational. It is emitted only while an
observation lease is active. Acquiring a lease first returns an atomic snapshot
of pressed keys and active Shortcut Press identities; closing it stops key
state observations. Shortcut Press terminal facts continue independently so
captured identities can always be released.

All events cross the platform/app seam with typed identities and enter the
same AppRuntime command queue. Runtime callback threads do not read guide
state.

The Shortcut Guide owns quarantine policy. It captures Shortcut Presses active
when the guide opens and every press started while it is open. A captured press
remains quarantined after the guide closes until its released or cancelled
terminal fact arrives. A new press after close receives a new identity and is
resolved normally.

Escape shares low-level timer and shutdown machinery but emits only
`InterruptionRequested`; it is not a Shortcut Press.

## Rejected Alternatives

### Keep identity internal to platform

Without identity at the lifecycle decision seam, guide quarantine must infer
operation boundaries from pressed-key snapshots. This recreates the ambiguity
that caused the bug.

### Put guide mode in the platform listener

This would couple an OS adapter to presentation policy and make the listener
decide whether an Action may execute. Guide policy remains in services/app.

### Preserve dual trigger and progress callbacks

Two callbacks do not provide one observable ordering and encourage callback
threads to query guide state. One typed stream makes ordering testable.

### End a press when modifiers are released

Modifier Context and Shortcut Press have different lifetimes. A Shortcut Press
ends on its function-key release or cancellation, allowing short invoke timing
and held speech composition to remain stable.

## Consequences

- Long timers validate the exact `ShortcutPressId`; a late timer cannot invoke
  a newer press.
- Stale recovery emits explicit identity-scoped cancellation.
- Listener shutdown remains silent and blocks late callbacks.
- No compatibility shim is retained for `ShortcutTriggered`,
  `ShortcutGestureProgressed`, `long_release`, or mixed Escape press types.
- Diagnostics may record press identity and phase, but not additional user
  text or input content.
