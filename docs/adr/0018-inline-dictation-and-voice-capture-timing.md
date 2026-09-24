# ADR-0018: Inline Dictation and capture timing ownership

## Status

Accepted. Amends ADR-0016's statement that PTT is the only global Voice Input interaction.

## Context

ClipAI needs a caret-free, two-press dictation path for external applications. The
existing PTT path creates a Voice Workflow and Review surface, so reusing its
Workflow membership for direct paste would couple independent interaction
lifecycles. The previous runtime also owned separate PTT and non-PTT deadline
schedulers plus silence timers, making stop and finalization ordering fragile.

## Decision

- `Ctrl+Alt+M` starts an inline capture and freezes the external Paste target at
  that press. The next press requests stop. The `VoiceInputController` alone
  owns the active capture and pending inline choice. A pending choice rejects a
  new capture until the user confirms or cancels it.
- Inline capture reuses the Voice engine and waveform but creates no Workflow.
  The controller emits typed presentation, paste, or discard effects. Raw paste
  uses the existing Output Operation, Paste Operation coordinator, and
  interactive worker. It reports Paste Dispatch truth, never confirmed success.
- Refinement uses the existing intent-preserving dictation Action through the
  provider execution module. Provider unavailability or refinement failure
  falls back to the original recognized text. The dictated text is data and
  instructions inside it are never executed as application commands.
- `VoiceCaptureTiming` owns the 120-second listening deadline, one-second
  countdown, two-second silence hint, and six-second stop/cancel settlement
  watchdog. It begins the deadline only after the matching engine reports
  Listening. Runtime observes each controller projection before executing its
  effects; it does not retain capture deadline or countdown state.
- Browser Speech promotes the last interim to a final segment on stop and
  discards it on cancel. Three consecutive self-ends without interim, audio
  above 0.02, or a new final segment stop restart. An empty settlement restores
  Review rather than submitting an empty finalization.

## Consequences

PTT retains its recoverable 120-second limit and Review behavior. Inline
Dictation is a separate explicit interaction. A terminal Paste acknowledgement
can be `failed`, `cancelled`, `dispatched_unconfirmed`, or `cleanup_failed`.
The waveform choice remains visible during asynchronous refinement, then
closes on the identity-scoped settlement command.

## Review trigger

Revisit if the engine supplies durable interim checkpoints, if more non-Workflow
voice destinations are added, or if users need to begin a second inline capture
while refinement is still running.
