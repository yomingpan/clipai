# Inline Dictation key propagation diagnosis (2026-09-27)

## Executive judgment

**Yellow; bounded local refactor; high confidence in the boundary, moderate confidence in the device outcome.** The same global listener recognizes `Ctrl+Alt+M` and Esc but previously allowed both physical keys to continue to LINE. The Win32 hook must decide propagation while the Voice Input controller remains the sole owner of the Inline interaction.

## Triggering evidence and protected behavior

- Fact: the user observed a literal `M` in LINE after `Ctrl+Alt+M`, then LINE closing when Esc cancelled Inline Dictation.
- Fact: `ClipAI/platform/hotkey.py` receives Windows low-level events, while `VoiceInputController.active_inline_interaction_id()` supplies the current interaction identity. `AppRuntime` routes Esc through `InterruptionRequested` to `cancel_inline_dictation()`.
- Inference: LINE handles the same physical key events after ClipAI observes them. A real LINE retest remains necessary.
- Preserve normal `M` typing, ordinary Esc outside Inline Dictation, exact Esc cancellation while Inline Dictation is active, and short/long shortcut ordering.

## Four-part diagnosis

1. **Owner:** `VoiceInputController` owns Inline interaction membership. The Windows hotkey adapter owns only whether a physical key propagates to another application.
2. **Capability:** selective suppression of ClipAI-consumed physical triggers is a reusable input-adapter capability, not a LINE branch.
3. **Boundary:** a read-only callback exposes the controller's active Inline identity at the platform seam. Neither platform nor UI owns a second interaction registry.
4. **Enforcement:** filter tests cover consumed `M` and Esc, normal typing, modifier chords, injected keys, key repeat, release after settlement, and ordered semantic delivery. The Inline contract records the propagation rule.

## Debt multiplier and options

The multiplier was an incomplete hook contract: recognizing an intent did not define physical propagation. Three more affected keys would otherwise invite three application-specific fixes. Leaving propagation unchanged is reversible but keeps visible side effects in LINE. Adding a separate native hook would duplicate key ordering and carry higher lifecycle risk. The chosen local refactor keeps one listener and centralizes suppression in its existing Win32 filter; it is reversible by removing that filter behavior.

## Intervention and migration

The filter suppresses `M` only for a configured exact `Ctrl+Alt+M` binding and exact Esc only while the controller reports an active Inline interaction. It posts the physical event to pynput's ordered listener queue before suppressing OS propagation. This uses pynput's Windows listener internals; dependency upgrades must rerun the filter tests and a physical LINE smoke test. No provider, paste, view, or Workflow policy moves to the filter.

Completion requires tests passing plus one physical LINE check that `M` is absent, Esc cancels Inline without closing LINE, and ordinary Esc still reaches LINE afterward. If a third key needs suppression, revisit whether the hook adapter should expose a general consumed-key policy rather than growing more trigger-specific fields.

## Concise ADR

**Context:** observed global keys also reached the foreground app. **Decision:** the existing Win32 filter handles OS propagation; the existing Voice Input controller answers whether Inline owns Esc. **Alternative:** a second keyboard hook was rejected because it would split event order and ownership. **Consequence:** the adapter depends on pynput's Windows event queue behavior and requires physical desktop validation. **Review trigger:** pynput upgrades or another consumed trigger key.
