# Native window surface contract

`NativeWindowSurface` is the only contract used by UI to ask about or change a
toolkit-owned window's native OS state.

- Callers pass a toolkit child id; the adapter resolves the top-level handle.
- The port covers task-switcher hiding, activation, no-activate show,
  foreground ownership, and window icon handle ownership.
- UI retains toolkit lifecycle (`deiconify`, `withdraw`, `winfo_id`,
  `focus_get`) and packaged icon resource discovery.
- The Windows adapter verifies foreground truth after activation and restores
  the previous foreground after a no-activate show.
- The Headless adapter returns conservative `False`/empty results.
- No adapter method raises when the OS fact is unavailable.
- Native pointer presses use the separately injected `PointerPressReader` and
  do not make UI a native API owner.

## External target activation

Application-owned top-level operations remain on `NativeWindowSurface`. An
external source window is represented separately by an opaque immutable
`ExternalWindowRef` captured by the foreground monitor. A platform
`ExternalWindowActivator` validates process/window identity, requests foreground
activation, waits for bounded foreground evidence and revalidates before
reporting success.

The activator does not read selection, clipboard or Panel state and does not
inject Paste. Runtime captures the reference at Panel open and supplies it to
open-time input preparation. Action selection consumes frozen input and does not
activate or recapture. Activation failure is typed and fail-closed: callers
must not switch to whichever window is currently foreground. Native window token
parsing, Win32 calls and polling remain in `platform/`.

The port accepts an optional immutable `ExternalWindowWaitPolicy` and an
`on_waiting` notification. A supplied policy bounds the complete activation call,
including its final confirmation, without resetting the deadline after native
activation. Notifications describe actual waiting and never request focus or
touch widgets. The Entry Panel caller shares a 3-second budget across activation
and post-capture confirmation, with notice after 500 ms; Paste continues to use
its existing default timings. Invalid identity returns `target_changed` (or
`target_gone` before activation); an otherwise valid target that fails to regain
foreground by the confirmation deadline returns `target_focus_timeout`.
See the selection-capture contract for projection, cancellation and stale-event
rules. A blocked native call is not preempted by the polling deadline.
