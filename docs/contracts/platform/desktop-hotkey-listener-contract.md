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
owned pressed tokens with physical Windows state. Owned tokens are registered
binding tokens, modifiers, Escape and Panel digits; ordinary unbound global
typing is never retained as shortcut state. Tokens explicitly reported released
are stale; unknown state is preserved only for owned tokens. Each affected
active Shortcut Press emits one `ShortcutPressEnded(..., "cancelled")`. The
revealing key may then participate in a fresh match, but stale recovery alone
does not produce a rejected-attempt event.

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

## Unified Entry Panel modifier hold

The listener owns one generic exact-modifier hold candidate for `Ctrl+Alt`.
Both modifiers down starts an identity-scoped 1.5 second deadline. Releasing either
modifier or pressing a non-modifier before the deadline cancels only that
candidate; an ordinary registered direct shortcut continues through its existing
Shortcut Press lifecycle.

At the deadline the listener must recheck the same hold identity and physical
modifier state before emitting `OpenUnifiedEntryPanel`. Once opened while the
modifiers remain held, top-row and numpad digits are claimed for typed Panel
digit commands and must not also create ordinary direct Shortcut Presses. The
claim ends when the modifier context ends.

Repeated exact holds while a Panel is already open emit an open/raise intent;
runtime decides whether to reuse the current lifecycle. Stale timers, injected
events, shutdown and recovered pressed-state cannot emit a late open or digit.
The listener never knows Panel category or Action IDs.
