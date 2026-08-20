# ADR-0010: Workflow runtime owns Voice capture destination admission

## Status

Accepted.

## Context

Global `Ctrl+Alt+W` and the Popup microphone both start Voice capture, but their
destination rules had diverged. `WorkflowRuntimeModule.admit_voice_shortcut()`
handled global focus and Workflow state while
`VoiceInputRuntimeModule._start_popup_capture()` repeated the status and
available-action matrix. Runtime also queried
`ResultDialogPresenter.voice_follow_up_is_visible()`, allowing a widget
visibility fact to decide Workflow policy.

The divergence required repeated coordinated changes across runtime, Voice
runtime, UI, and tests when Follow-up became a capture destination. An open
Follow-up is semantic user intent, while its widget visibility is presentation
state; the two must not be interchangeable.

## Decision

`WorkflowRuntimeModule` is the single owner of Voice capture destination
admission for both global shortcuts and Popup microphone intents. Both triggers
submit a typed `VoiceCaptureIntent` through one admission interface and receive
one typed `VoiceCaptureAdmission`.

After trigger-specific Workflow lookup and focus validation, both intents pass
through the same visible-Workflow destination matrix. Separate shortcut-only
and Popup-only private admission pipelines are not permitted.

UI reports an immutable `VoiceCaptureSurfaceContext` at explicit intent time.
It carries the semantic Follow-up request and current Voice Draft selection;
runtime does not read widget-visibility-named methods. The owner validates this
context against Workflow membership, confirmed focus, active capture,
invocation state, available actions, and trigger semantics.

Trigger semantics remain intentionally distinct:

- `Ctrl+Alt+W` targets an explicitly opened Follow-up before Voice Review.
- The Popup microphone continues Voice Review even when Follow-up is open.
- Both triggers target Follow-up from an eligible completed result.
- Provider-active or invalid Workflows reject capture; only the global shortcut
  may create a new Voice Draft when no visible Workflow exists.

`VoiceInputRuntimeModule` executes the admission result. It does not inspect
Workflow status or select a destination.

## Alternatives

- Keep two admission paths. Rejected because every new destination would repeat
  policy and tests across both paths.
- Let UI send the final destination. Rejected because UI would become a second
  Workflow policy owner and could bypass runtime validation.
- Move admission into `VoiceInputController`. Rejected because that controller
  owns microphone capability and capture lifecycle, not visible Workflow
  membership, Foreground Workflow, or Popup focus truth.

## Consequences

- Destination rules have one interface and one owner.
- UI reports semantic context without deciding admission.
- The Popup and shortcut entry points retain their approved product behavior.
- A table-driven destination matrix and AST architecture safeguard detect
  duplicate status policy or widget visibility leakage.

## Review trigger

Revisit this decision before supporting a second simultaneous visible Popup, a
second capture engine with different destination semantics, or a new Voice
destination that cannot be expressed using current Workflow and surface facts.
