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
inject Paste. Runtime captures the reference at Panel open and supplies it at
explicit Action selection. Activation failure is typed and fail-closed: callers
must not switch to whichever window is currently foreground. Native window token
parsing, Win32 calls and polling remain in `platform/`.
