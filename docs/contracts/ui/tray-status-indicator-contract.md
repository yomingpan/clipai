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
- Every accepted provider configuration projection synchronizes the baseline
  from the coordinator's active binding, including successful save, selection
  and reload. Pending/failed/stale completion does not invent readiness.
  Readiness changes do not replace active processing, a success flash or a
  sticky error; the lifecycle owner applies the new baseline on settlement.

Concurrent, timer-reset, late-event, icon retry, menu callback, and stop cleanup behavior must be covered by tests.

## Speech Speed menu

- `Speech Speed: <saved preset>` remains a first-level menu with one-level radio choices. Its parent shows the saved value without opening the submenu.
- The mutually exclusive choices are Slow, Normal, Fast, and Super Fast, mapped to `-25%`, `+0%`, `+25%`, and `+50%`.
- The selected item cannot submit a duplicate update. While saving, all choices are disabled and the parent shows the saved preset with `(Saving...)`; failure restores the previous authoritative selection.
- Unavailable speech disables all choices and shows the saved preset with `(Unavailable)`. An unmatched legacy rate shows `Speech Speed: Custom` until a preset is selected.

## Quick-control menu depth

- Tray labels use English. The official Action Language Pack display names are `Traditional Chinese` and `Japanese`; Action content still follows its selected pack.
- Voice Input stays a first-level category. Its submenu contains one state-aware Enable/Disable command and direct language radio choices, without a nested Language menu. Pending setup/disable is disabled and named explicitly; failed cleanup offers a retry of Disable. The parent shows the authoritative capability and saved language. A language save projects `(Saving...)` while the prior language stays checked; save failure retains that choice and notifies the user.
- Inline Dictation is a first-level category beside Voice Input. Its submenu directly offers input-mode and placement radio choices; the parent shows the saved input mode and any pending save.
- Quick controls may have one submenu level. Provider credentials and personal-style editing keep their dedicated dialogs.
