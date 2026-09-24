# Inline Dictation contract

`ToggleInlineDictation` starts capture with a frozen `VoiceInlineTarget` and
requests stop when that capture is live. Capture admission is refused while any
capture or unresolved inline choice exists. No provider call or paste follows
from opening, rendering, focusing, or closing the window.

The controller owns recognized segments and the pending choice. On stop, a
targeted nonempty result emits `PresentInlineChoice`. Without a Paste target,
or after cancellation, it emits `DiscardInlineDictation`. Empty recognition
returns a retryable state. `ConfirmInlineDictation` emits one paste effect and
consumes the choice. `InterruptCurrent` and `InterruptAll` attempt inline
cancellation before other interruption handling.

Raw confirmation schedules a non-Workflow Paste Operation using the frozen
target. Refined confirmation leaves the window in a visible refining state
until the provider result settles. Missing provider readiness, provider error,
or cancellation uses the original text. The operation and its late settlement
are scoped by the inline capture identity; a late refinement cannot close a
newer window.

The engine's stop path promotes the last interim segment once before `ended`.
Cancel and shutdown discard that interim. An unresponsive stop or cancel is
settled by a six-second watchdog as a retryable timeout; no success is
fabricated. The 120-second limit starts at Listening and remains fixed.
