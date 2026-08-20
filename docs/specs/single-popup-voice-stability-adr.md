# ADR: Single Popup surface and Voice permission stability

## Context

Multiple pinned Popups made Popup lifetime, semantic Foreground Workflow,
native Windows focus, Voice capture, and Paste targets compete at once. A
WebView2 helper window could also enter the foreground during microphone
permission setup and be observed as an external paste target.

## Decision

- ClipAI permits exactly one visible Workflow Popup surface. PIN reserves that
  surface, so every subsequent visible Action reuses the pinned Workflow and
  Popup instead of being rejected or creating another Popup. Reuse preserves
  PIN state, cancels the superseded provider invocation and speech owned by the
  replaced content, and keeps the Workflow's captured provider binding.
- `Ctrl+Alt+W` never creates a second Popup while a visible Workflow already
  owns the surface. An active Voice capture continues. When that Popup has
  confirmed focus, Voice Review receives another Draft insertion and a
  completed result receives a Follow-up insertion at the live caret; settled
  speech is never submitted automatically. Provider-active or Follow-up-
  unavailable results reject the shortcut with explicit feedback. A visible
  but unfocused Popup must be focused or closed before the shortcut can start.
  Only the absence of a visible Popup creates a fresh Voice Draft.
- Voice capture does not require an external editable window to be focused.
  When no target can be captured, the Voice Draft starts without one and Paste
  resolves the latest observed external target only when the explicit Paste
  operation begins.
- `WorkflowRuntimeModule` owns visible-surface admission. Voice runtime must
  request an admission decision before capturing an optional external target,
  creating a Voice Workflow, or reusing the visible Workflow.
- Popup attention has an identity and reports whether native and toolkit focus
  were actually acquired. Failed focus repeats the warning through the notifier.
- WebView microphone consent is allowed only for an explicit Voice Setup or an
  admitted Push-to-Talk capture, using a non-activating tool surface. Stop,
  cancel, and all unknown helper requests fail closed. This supports WebView2
  runtimes that re-request microphone access when capture begins after setup.
- Before an admitted capture starts, the platform host first applies that
  non-activating native style and then performs pywebview's `show()` lifecycle
  transition. A raw off-screen native show is insufficient for Web Speech to
  enter Listening. The page hides the helper as soon as Listening begins; the
  host must not restore or explicitly focus it.
- The Browser Speech helper process is registered as app-owned and can never be
  selected as a `PasteTarget`.

## Consequences

The product no longer supports multiple simultaneously visible pinned result
Popups. Existing voice-enabled preferences remain valid; a missing or revoked
permission requires repair only when it is actually encountered. Any future
request for multiple visible result Popups requires a new ADR covering focus,
Paste, and lifecycle ownership before implementation.
