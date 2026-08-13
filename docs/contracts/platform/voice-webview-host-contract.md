# Voice WebView host contract

The browser speech host is infrastructure, not an application surface.

- `prepare` and `start` are explicit microphone intents and must realise the
  WinForms host before sending JavaScript to the page.
- Realisation keeps `Opacity=0`, applies non-activating tool-window extended
  styles, and uses native WinForms `Show()`; it never calls pywebview `show()`.
- A `System.IntPtr` handle is converted with `ToInt64()`.
- Failure to realise emits `initialization_failed` and the command's terminal
  event; no page command is sent.
- Work already on the WinForms UI thread executes directly. Only callers on a
  different thread are marshalled with `Invoke`.
- Unit doubles record calls and preserve the real `IntPtr` conversion behavior.
  Only the 20 ms Windows watcher may make a claim about visible or opaque frames.
