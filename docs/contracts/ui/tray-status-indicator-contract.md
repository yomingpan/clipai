# Tray Status Indicator Contract

Tray is a dumb, injected UI adapter. It renders `ApplicationStatus`, memory state, and menu callbacks; it does not infer application state or own lifecycle timers.

## Ownership

- `OperationLifecycleCoordinator` is the single owner of processing/success/error timing.
- LLM and TTS report through `OperationTracker`; providers and presenters never drive tray directly.
- Tray owns only the pystray thread, icon lock, OSError retry, memory pixel, menu construction, and icon cleanup.
- Tray projects authoritative `SpeechSpeedState` and emits `SetSpeechSpeed`; it never persists preferences or changes the checked item optimistically.
- `Export Diagnostics` and Quit only enqueue typed commands through injected callbacks.

## Projection

- Any active operation: processing orange.
- Last operation succeeds: success green for two seconds, then readiness baseline.
- Failure: error red for three seconds; if work remains, return to processing.
- Cancellation: no success flash.
- Ready baseline: idle blue. Not-ready baseline: warning yellow.

Concurrent, timer-reset, late-event, icon retry, menu callback, and stop cleanup behavior must be covered by tests.

## Speech Speed menu

- `Speech Speed` follows `Keyboard Shortcuts...`; a separator divides it from `Usage Guidance`.
- The mutually exclusive choices are Slow, Normal, Fast, and Super Fast, mapped to `-25%`, `+0%`, `+25%`, and `+50%`.
- The selected item cannot submit a duplicate update. While saving, all choices are disabled and the parent reads `Speech Speed (saving...)`; failure restores the previous authoritative selection.
- Unavailable speech disables all choices and projects `Speech Speed (unavailable)`. An unmatched legacy rate projects `Speech Speed (Custom)` until a preset is selected.
