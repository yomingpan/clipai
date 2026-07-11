# Operation Lifecycle Contract

External LLM and TTS work is registered with a stable operation ID and kind. `OperationHandle.succeed()`, `fail()`, and `cancel()` are idempotent; late completion after stop or replacement has no effect.

The coordinator is thread-safe, owns transient timers, and projects all active operations onto one `StatusIndicator`. Feature code must not add local tray precedence rules or reset timers.

Global hotkey speech uses a unique `tts:clipboard:<uuid>` operation ID per trigger. Replacement cancels the previous handle before registering the new work. Empty prepared text is a successful no-op; adapter exceptions fail the operation. A cancelled or replaced job must never report late success.
