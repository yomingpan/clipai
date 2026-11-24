# Inline Dictation lifecycle diagnosis

Status: historical diagnosis; production migration in progress. Decision: [ADR-0019](../adr/0019-inline-dictation-interaction-lifetime.md).

## Executive judgment

**Yellow — incremental migration. Confidence: high.** The current capture and
choice owner is sound, but ownership ends before refinement and Paste settle.
Another local flag in the window or runtime would multiply admission,
cancellation, and late-completion rules. Extend the existing owner through the
terminal acknowledgement and route typed effects through the existing task
owners.

## Triggering evidence

### Verified facts

- `VoiceInputController.confirm_inline_settlement()` clears `_pending_inline`
  before emitting `PasteInlineDictation`; `request_capture()` rejects only an
  active capture or pending choice (`ClipAI/services/voice_input.py:313-350`).
- Runtime can therefore admit a second `Ctrl+Alt+M` capture while refinement is
  pending (`ClipAI/app/runtime_voice_input.py:171-193`). The inline presenter
  retains one window (`ClipAI/ui/result_dialog.py:404-413`).
- `InlineDictationCoordinator` maps provider cancellation to the same raw-text
  Paste fallback as a provider error (`ClipAI/app/inline_dictation.py:49-70`).
  During refinement, `cancel_inline()` finds neither capture nor pending choice
  (`ClipAI/services/voice_input.py:343-350`).
- `VoiceInlineTarget.workflow_id` carries the inline capture ID even though the
  target is explicitly non-Workflow (`ClipAI/core/voice.py:183-188`,
  `ClipAI/app/runtime_voice_input.py:184-187`). The corresponding field also
  scopes the provider completion and window close.
- Inline Paste invents a Workflow-shaped ID for `OutputOperationIntent` and
  `PasteRequest` (`ClipAI/app/runtime_outputs.py:225-253`). The Popup presenter
  discards output acknowledgements without a Workflow view
  (`ClipAI/ui/result_dialog.py:490-497`), so the inline window closes before
  Paste settlement.
- The existing targeted tests pass: 33 passed across
  `tests/app/test_inline_dictation.py` and
  `tests/app/test_runtime_voice_input.py` on 2026-09-24. They do not cover
  refinement → Esc → late callback, a second capture during refinement, or
  inline Paste terminal presentation.

### Inference

The debt multiplier is **an interaction whose semantic lifetime is shorter
than its external operations**. Each new post-capture step would need another
busy check, close guard, cancellation exception, and ad hoc correlation field.
The present tests establish isolated callback behavior, not the combined
interaction sequence.

## Current capability and protected behavior

`Ctrl+Alt+M` freezes an external target, starts Voice capture, and stops it on
the next press. The current choice-based flow explicitly chooses raw or refined
Paste. ADR-0019 also specifies an optional minimal mode: a short stop requests
raw Paste and a long stop requests refinement, without a normal-path choice
window. Refinement uses the existing intent-preserving Action; provider
unavailability or error preserves recognized text for explicit recovery rather
than automatically pasting it. The one container-scoped clipboard
transaction owner and Paste Operation coordinator retain dispatch and cleanup
truth. Inline Dictation does not create a Workflow. These behaviors remain.

## Four-part diagnosis

1. **Owner.** `VoiceInputController` owns Inline Dictation capture and choice
   today and is already named as lifecycle owner in
   `docs/ARCHITECTURE_BOUNDARIES.md`. Its semantic lifetime should include
   refinement, Paste pending, acknowledgement, and discard. Runtime only routes
   effects and completions. Provider and Paste modules keep their existing
   task and operation ownership.
2. **Capability.** Identity-scoped progression from explicit capture to an
   external operation's terminal acknowledgement is reusable orchestration,
   not a window-specific exception. Explicit discard is a distinct Paste
   cancellation intent because it must preserve the prior clipboard, while
   ordinary failed Paste preserves result text for recovery.
3. **Propagation.** A capture ID currently crosses a field named `workflow_id`,
   provider callbacks directly request Paste, and a Popup-only output presenter
   loses non-Workflow acknowledgements. These facts force callers to know
   which phase is actually live and where completion should appear.
4. **Enforcement.** Public transition tests must cover capture → choice →
   refinement → Paste terminal, second-capture rejection, Esc at each phase,
   late callbacks, and clipboard recovery. Architecture tests should reject a
   second inline lifecycle registry, provider-task ownership outside
   `ProviderExecutionModule`, and another clipboard or Paste owner. Typed
   origins and identities should make Workflow/capture substitution detectable.

Three similar future changes would each add a separate admission guard,
completion callback, and window rule, yielding stale closes or Paste after Esc
that pass isolated unit tests.

## Realistic options

| Option | Benefit | Cost and risk | Reversibility |
| --- | --- | --- | --- |
| Keep current split | No migration | Esc and late completion remain ambiguous | High |
| Add a runtime busy flag | Small patch | Second lifecycle owner and duplicated cancellation truth | Medium |
| Extend `VoiceInputController` with typed effects and acknowledgements | One semantic owner and one public test seam | Requires coordinated core, app, UI, and Paste contract changes | High in staged commits |
| Rebuild Voice and Paste modules | Uniform model | Disproportionate risk to settled owners | Low |

**Primary option:** incremental migration of the existing controller and its
typed completion seam. No new provider executor, Paste coordinator, clipboard
transaction owner, or global event mechanism is introduced.

## Reversible migration sequence

1. Characterize current behavior with tests for confirmed choice, provider
   success/failure, Paste acknowledgement, Esc, and late completion. Keep the
   original code path passing until a stage is replaced.
2. Give the non-Workflow interaction a truthful identity, a mode frozen at
   start, and typed phases in `VoiceInputController`. Its public transitions
   decide admission, explicit discard, raw-text recovery, and terminal
   presentation. Keep provider and
   Paste identities distinct and reject acknowledgements that do not match.
3. Route provider completion through the typed runtime queue before deciding
   whether to Paste. Remove callback-driven Paste and close effects from the
   old path in the same stage; a cancelled interaction must ignore late work.
4. Route inline Paste acknowledgements back to the controller. Express
   explicit discard before Paste Dispatch through the existing Paste owner;
   ordinary failure still follows clipboard recovery, while cleanup failure
   triggers no fallback clipboard write and warns about uncertain restoration.
   Remove the synthetic Workflow lookup
   from inline presentation.
5. Project refining, Paste pending, `dispatched_unconfirmed`, and persistent
   failure from controller state. Choice-based mode renders its choice surface;
   minimal mode renders compact non-activating status in the normal path and an
   actionable recovery surface on failure. Neither view decides operation
   success. An old notice may close only its own interaction's view lease.
6. Remove obsolete callback paths, names, and tests. Run targeted, architecture,
   unit, integration, and Windows smoke gates appropriate to the cross-layer
   change.

The migration is complete when Esc during refinement cannot cause Paste; a new
capture can start immediately after accepted refinement discard; all late
provider and Paste completions are identity-checked; a second capture is
rejected while refinement or Paste is live; and the inline window reflects the
real Paste terminal acknowledgement without claiming success.

## Uncertainty and next evidence

The current tests do not measure the real Windows timing between Paste Dispatch,
clipboard restoration, and a user pressing Esc. A focused Windows smoke test
with a real external target is the highest-value evidence after the typed
transition tests pass. It must distinguish not-dispatched cancellation from
`dispatched_unconfirmed` and confirm that explicit discard leaves the prior
clipboard intact.
