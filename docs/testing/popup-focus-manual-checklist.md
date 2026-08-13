# Popup focus manual verification

Run on an interactive Windows desktop with
`logging.diagnostics.focus_transitions: true`. For each row, confirm the log
contains native foreground, toolkit focus, and projection values.

- Open a Popup normally: both evidence axes become true and projection becomes
  focused within one 25 ms UI tick.
- Force Windows to reject activation while Tk emits `<FocusIn>`: projection
  stays unfocused and the initial-focus gate remains closed.
- Alt+Tab to another application: the Popup releases focus; an unpinned Popup
  closes and a pinned Popup remains visible but unfocused.
- Click another application's taskbar button: expect the same result without
  requiring Tk `<FocusOut>`.
- Let another application take foreground programmatically: expect the same
  result without an outside pointer event.
- Start Paste: foreground loss while Paste is active must not emit a second
  close/release transition.
- Open Provider Settings or Shortcut Guide: foreground loss while the owned
  dialog is active must be suppressed; closing the dialog restores through the
  owned-dialog transition.
