# Application process lifecycle ADR

## Context

ClipAI requires one desktop runtime and may create an isolated Voice WebView2
helper. A second desktop launch previously created another Tk root, Tray,
hotkey listener, provider runtime, and Voice helper. A Voice helper could also
survive when its parent disappeared without sending the protocol shutdown
command because stdin EOF ended only its reader thread while the WebView
mainloop remained alive.

## Decision

- Application-instance admission happens before configuration loading or any
  desktop runtime resource is constructed.
- A user-session-scoped Windows named mutex implements that admission behind
  the `ApplicationInstanceGate` interface. The first process holds an
  idempotent lease for its complete runtime lifetime. A second process shows an
  explicit already-running startup message and exits without constructing an
  `AppRuntime`.
- `AppRuntime` remains the single owner of normal desktop runtime shutdown.
- `BrowserSpeechWebView2Engine` remains the single owner of the Voice helper
  process and transport. The helper treats parent-transport EOF as terminal,
  and engine cleanup uses bounded graceful, terminate, and kill settlement.
- `ProviderExecutionModule` settles cancellation cleanup for its loop-owned
  provider tasks before closing the shared HTTP transport. Task settlement and
  transport close are bounded; a timeout is diagnostic evidence but must not
  escape into Tk or prevent the remaining application cleanup.
- `AppOwnedProcessRegistry` remains a focus-exclusion registry. It is not a
  process supervisor and does not own process termination.

## Alternatives

- A global process manager was rejected because it would duplicate the
  existing Voice engine and runtime ownership paths.
- Windows Job Object containment is deferred because there is currently one
  helper process and stdin EOF directly addresses the observed orphan. It is
  the next containment option if the bounded contract proves insufficient.
- Cross-process activation was deferred. The second launch provides visible
  feedback but does not add an IPC command channel merely to focus an existing
  Tray application.

## Consequences

Normal Voice setup, capture, persistent microphone permission, non-activating
WebView behavior, and Paste-target exclusion remain unchanged. Startup gains a
small platform seam and one OS handle. Abnormal parent exit no longer depends
on product-layer cleanup running.

Tests must cover instance admission, idempotent lease release, stdin EOF,
terminate/kill settlement, transport closure, and exit races. Interactive
Windows smoke testing remains responsible for proving real WebView2 behavior.

## Review trigger

Introduce a platform-owned Windows Job Object containment adapter if an orphan
helper is observed again after this change, or before adding a second category
of helper process. Revisit cross-process activation only when the product has a
stable control surface that a second launch can meaningfully reveal.
