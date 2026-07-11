# Tray Status Indicator Contract

Tray is a dumb, injected UI adapter. It renders `ApplicationStatus`, memory state, and menu callbacks; it does not infer application state or own lifecycle timers.

## Ownership

- `OperationLifecycleCoordinator` is the single owner of processing/success/error timing.
- LLM and TTS report through `OperationTracker`; providers and presenters never drive tray directly.
- Tray owns only the pystray thread, icon lock, OSError retry, memory pixel, menu construction, and icon cleanup.
- `Export Diagnostics` and Quit only enqueue typed commands through injected callbacks.

## Projection

- Any active operation: processing orange.
- Last operation succeeds: success green for two seconds, then readiness baseline.
- Failure: error red for three seconds; if work remains, return to processing.
- Cancellation: no success flash.
- Ready baseline: idle blue. Not-ready baseline: warning yellow.

Concurrent, timer-reset, late-event, icon retry, menu callback, and stop cleanup behavior must be covered by tests.
