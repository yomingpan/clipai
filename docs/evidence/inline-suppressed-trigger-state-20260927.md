# Inline suppressed-trigger hold diagnosis (2026-09-27)

## Executive judgment

**Yellow; local adapter repair; high confidence in the repeated reset, moderate confidence in the Windows mechanism.** Two attended fixed-WAV Minimal-refine attempts ended as `short` after the operator held `Ctrl+Alt+M`. The same runs logged repeated stale-state resets for `m` while its key-down events repeated. The existing hotkey dispatcher must own the press lifecycle; the native filter only decides OS propagation.

## Evidence and protected behavior

- Fact: `artifacts/inline-controlled-audio-refine-minimal-1/inline-trace.log` and `...-2/inline-trace.log` contain `stop_requested outcome=short` and no `refine_requested`. Both WAV intervals passed the Listening-to-Stop timing check. The first target received no Paste event; the second received one raw Paste. Neither report is a refine pass.
- Fact: `logs/clipai.log` repeatedly says `Discarding stale hotkey state ... tokens=['m']` during both physical holds. The operator confirmed that M itself remained pressed. The Win32 filter in `ClipAI/platform/hotkey.py` suppresses M to prevent its insertion in LINE, then forwards the event to the existing pynput semantic queue.
- Inference: `GetAsyncKeyState(M)` reads false while the native hook suppresses M. The deterministic test reproduces that returned value and the resulting timer cancellation, but the desktop log does not independently record the API return value.
- Preserve ordinary M typing, suppression only for exact `Ctrl+Alt+M`, short-press behavior, long-press behavior, Esc ownership, injected-key rejection, and recovery after a missing release.

## Four-part diagnosis

1. **Owner:** `_HotkeyDispatcher` owns pressed tokens, one timer, and one press identity. `_WindowsHotkeyEventFilter` owns native propagation. `VoiceInputController` owns the resulting Inline interaction.
2. **Capability:** the physical state of a key consumed by a native hook is not a reliable release oracle. That is an adapter capability, not a LINE or Inline workflow exception.
3. **Boundary:** the registration point passes the hook's suppressed-trigger metadata to the dispatcher. No second hold registry or application callback is added.
4. **Enforcement:** platform tests inject false asynchronous M state during repeated key-downs, require one long invocation, and verify stale suppressed state clears before a later chord. A registered-listener test verifies production wiring.

## Debt multiplier and options

The multiplier is conflicting observations of one key: the hook reports a held press while asynchronous polling reports release. A third suppressed trigger would otherwise invite another token-specific exception. Accepting the false release keeps broken long presses. A second keyboard hook would split event order and ownership. The local repair lets the dispatcher use hook release for suppressed triggers, while retaining asynchronous checks for other keys; it is reversible by removing the suppression metadata if the native approach changes.

## Intervention and migration

`register_hotkeys_with_long_press()` computes the exact `Ctrl+Alt+M` suppression flag once and passes `m` as an unobservable physical trigger to the dispatcher. The long timer and stale-state scan do not cancel that active trigger based on asynchronous M state. If the chord's modifiers are subsequently absent, stale M state is cleared before a new chord. The change stays inside the platform adapter; no Voice Input, provider, Paste, clipboard, or UI owner moves.

Completion requires deterministic tests, the non-integration suite, and an attended Minimal-refine fixed-WAV run with `stop_requested outcome=long`, `refine_requested`, one controlled-target Paste, and restored clipboard. The first two failed runs remain evidence. If physical M release is missed while modifiers remain held, the hook cannot distinguish that case from a continuing hold; a future independent HID observer should exercise it.

## Concise ADR and review trigger

**Context:** a suppressed trigger and asynchronous polling disagree during physical holds. **Decision:** the existing dispatcher trusts hook release for configured suppressed triggers. **Alternative:** permit M propagation or add a second native hook; both violate verified behavior or event ordering. **Consequence:** missing hook releases rely on the next modifier/shortcut transition for cleanup. **Review trigger:** another suppressed trigger, a pynput upgrade, or an attended hold that still resolves as short.
