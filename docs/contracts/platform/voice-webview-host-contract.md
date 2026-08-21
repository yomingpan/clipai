# Voice WebView host contract

The browser speech host is infrastructure, not an application surface.

## Ownership and process lifecycle

- `BrowserSpeechWebView2Engine` is the single owner of the helper process and
  its stdin/stdout transport. `AppRuntime` owns only the injected Voice engine
  lifecycle and must not retain a concrete process handle.
- A protocol `shutdown` command and stdin EOF are both terminal host events.
  EOF means the parent transport no longer exists; the host destroys its
  WebView and exits without waiting for another command.
- Engine shutdown attempts protocol shutdown first, then bounded terminate and
  kill fallback. Every fallback confirms settlement where possible, closes the
  transport pipes, and must not prevent the rest of application shutdown when
  process exit races with cleanup.
- Process ownership is unregistered only after the engine has completed its
  bounded settlement and transport cleanup.

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
