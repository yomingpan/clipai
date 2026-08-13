# ADR-0005: Realise the voice WebView host invisibly

## Status

Accepted.

## Context

The browser speech engine needs a realised WebView2 window for `getUserMedia()`
and its permission request to settle, but that infrastructure window is not a
user surface. The previous helper converted `System.IntPtr` with `int()`, which
raises `TypeError` under pythonnet 3. A broad exception returned `False`, the
caller ignored that result, and `window.show()` then called WinForms
`Show()` plus activation with opacity restored to 1 by pywebview. The result was
an opaque blank frame during `Ctrl+Alt+W`.

## Decision

`realise_voice_host_invisibly()` converts the native handle with
`IntPtr.ToInt64()`, sets `Opacity=0.0`, applies only the
`TOOLWINDOW | NOACTIVATE`/not-`APPWINDOW` extended style through Win32, and calls
the WinForms native `Show()`. It does not call pywebview `show()`, `ShowWindow`,
or move the window off-screen.

Both `prepare` and `start` must successfully realise the host before a page
command is sent. Failure emits that command's terminal `initialization_failed`
event. Native work runs directly when already on the WinForms UI thread and is
marshalled only when `InvokeRequired` is true.

## Measurements

The supplied Windows experiment sampled all process-owned visible windows every
20 ms for four runs per strategy:

| Strategy | Opaque frames | End state / outcome |
| --- | ---: | --- |
| `Opacity=0` then WinForms `Show()` | 0 in each run | realised and invisibly retained |
| `ShowWindow` only | 0 in each run | layered state no longer retained |
| move to `(-32000, -32000)` | non-zero | Windows clamps the window into the virtual desktop |
| never realise | 0 in each run | `getUserMedia()` never settles |

The pre-fix deterministic regression loop reported four relevant failures:
IntPtr realisation returned `False`, only one of two commands attempted
realisation, the failing prepare still sent one JavaScript command, and start
called pywebview `show()`. After the change the focused file reports 10 passing
tests in 0.13 s. `scripts/app_flash_watch.py` preserves the 20 ms OS-level
measurement loop for release verification; its observations are evidence, not
a simulated Windows claim.

## Rejected alternatives

- `ShowWindow(SW_SHOWNOACTIVATE)` avoids activation but does not leave opacity
  owned by the WinForms window.
- Off-screen positioning is not stable because Windows can clamp the position.
- Not realising the host prevents a visible flash but leaves microphone setup
  without a terminal event.
- Always using `Control.Invoke` can deadlock a permission callback already
  running on the WinForms UI thread.

## Consequences

- Browser speech can settle permission and media setup without a user-visible
  infrastructure window.
- A failed native realisation becomes an explicit terminal operation failure.
- Native failures print a traceback to stderr instead of disappearing behind a
  boolean that callers ignore.
- Release verification still requires an interactive Windows measurement; unit
  doubles record requested native operations and deliberately do not claim to
  simulate compositor behavior.
