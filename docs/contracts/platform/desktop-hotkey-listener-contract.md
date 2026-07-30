# Platform Desktop Hotkey Listener Contract

## Intent

`ClipAI/platform/hotkey.py` translates physical desktop keyboard input into an
ordered stream of typed Shortcut lifecycle facts. Its quality standard is
predictable user intent: uncertain or stale physical state must never cause an
unrelated Action.

## Boundary and ownership

The platform hotkey module owns:

- key normalization and registered binding matching;
- current Modifier Context and pressed physical keys;
- one distinct `ShortcutPressId` per complete binding match;
- the 500 ms short/long threshold and timer validation;
- stale physical-state recovery;
- OS listener and timer shutdown;
- observation leases for guide key visualization.

It does not resolve Actions, providers, prompts, output routes, UI, guide
quarantine, speech composition, or Workflow policy.

## Canonical lifecycle

A Shortcut Press begins when a complete registered binding first matches. It
ends when every non-modifier function key for that binding is released or when
the physical operation is cancelled. Keeping Ctrl, Alt, or Shift held does not
extend the identity and does not cause a later function-key press to reuse it.

The registrar accepts one callback:

```python
on_event(event: ShortcutInputEvent)
```

The ordered union contains:

- `ShortcutKeyStateChanged(pressed_keys)` — observational key state;
- `ShortcutPressStarted(press_id, shortcut_id)`;
- `ShortcutPressInvoked(press_id, shortcut_id, press_type)` where press type is
  only `short` or `long`;
- `ShortcutPressEnded(press_id, shortcut_id, outcome)` where outcome is
  `released` or `cancelled`;
- `ShortcutAttemptRejected()`;
- `InterruptionRequested(scope)` where scope is `current` or `all`.

There is no `long_release`, generic `cancel`, or Escape value in the Shortcut
Press type.

## Timing and ordering

- Short invoke occurs on non-modifier function-key release, immediately before
  `ShortcutPressEnded(..., "released")`.
- Long invoke occurs when the 500 ms threshold is reached. Function-key release
  later emits only the terminal fact.
- Releasing a modifier before the function key does not invoke or end the
  Shortcut Press.
- Every long timer captures and validates its exact `ShortcutPressId`.
- Q speech composition and its Action key are independent, overlapping
  Shortcut Presses with different identities.
- Escape emits `current` immediately and `all` at the long threshold. It never
  emits Shortcut Press lifecycle facts.

## Observation lease

`observe()` atomically:

1. enables `ShortcutKeyStateChanged` delivery;
2. returns `ShortcutObservationSnapshot` containing current pressed keys and
   active Shortcut Press references.

Closing the lease stops observational key-state events. Started, invoked, and
terminal lifecycle facts are never suppressed by observation state.

## Recovery and shutdown

Before matching a normalized non-injected key-down, the module reconciles
known pressed tokens with physical Windows state. Tokens explicitly reported
released are stale; unknown state is preserved. Each affected active Shortcut
Press emits one `ShortcutPressEnded(..., "cancelled")`. The revealing key may
then participate in a fresh match, but stale recovery alone does not produce a
rejected-attempt event.

`stop()` is idempotent and completely silent. It cancels timers, clears state
and observers, stops the OS listener, and prevents keyboard or timer callbacks
from emitting late facts.

Injected events never mutate physical state or emit facts.

## User trust red lines

When state is uncertain, priority is:

1. avoid unintended Actions;
2. cancel ambiguous active presses explicitly;
3. restore a clean physical state for the next real press;
4. avoid guessing intent.

## Tests

- `tests/platform/test_hotkey.py`
- `tests/platform/test_hotkey_edge_cases.py`
- `tests/platform/test_shortcut_press_lifecycle.py`
- `tests/app/test_hotkey_shortcut_recovery.py`
- `tests/app/test_runtime_shortcut_guide.py`

These cover normalization, short/long ordering, modifier-first release, unique
identities under held modifiers, overlapping speech composition, stale
cancellation, timer races, observation leases, Escape separation, shutdown,
and the guide-close regression.
