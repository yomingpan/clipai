# ADR-0016: Recoverable PTT safety limit

## Status

Accepted.

## Context

The 120-second missing-release watchdog treated expiry as user cancellation.
That discarded finalized recognition even though the user had not asked ClipAI
to abandon the capture. A UI-only countdown would also duplicate the runtime
deadline and could disagree with the actual stop.

## Decision

- Push-to-talk remains the only global Voice Input interaction. There is no
  automatic continuation or long-form mode.
- The 120-second limit starts only after the matching engine reports Listening.
- Runtime schedules one authoritative monotonic deadline and sends typed
  countdown observations. `VoiceInputController` validates the press identity,
  owns the projected remaining time, and decides settlement. The UI keeps its
  Listening lifecycle label stable and appends the countdown reminder to the
  Listening status during the final 30 seconds.
- Limit expiry uses the existing bounded stop/finalization path, preserves
  contiguous finalized segments, and never submits or pastes them.
- A timed-out press must be released before another PTT capture is admitted.
- Explicit user cancellation continues to discard the active capture. Transport
  failure preserves any contiguous finalized segments and reports the failure.

## Alternatives

- Extend or configure the limit: rejected because it postpones rather than
  prevents catastrophic content loss.
- Add a toggle-based long-form mode or automatic restart: rejected because it
  expands interaction complexity and microphone privacy risk.
- Let the UI own a timer: rejected because it creates a second deadline owner.

## Consequences

The PTT interaction remains unchanged for captures under two minutes. Longer
captures become recoverable checkpoints with visible countdown and explicit
re-press friction. Interim-only recognition still depends on the engine's
bounded finalization support; finalized segments are never discarded by a
system-originated terminal failure.

## Review trigger

Revisit this decision if the recognition engine exposes durable interim
checkpoints, if telemetry shows material finalization loss at the boundary, or
if a second Voice Input interaction is proposed.
