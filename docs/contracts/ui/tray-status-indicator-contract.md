# Tray Status Indicator Contract

The tray is an injected UI adapter for application status. Providers and UI presenters must not drive it through globals or an Event Bus.

## Status semantics

- `idle`: no external API call is active.
- `processing`: an external LLM or TTS call has been sent and is waiting or running.
- `success`: the external call returned successfully; the tray resets to idle after the configured delay.
- `error`: the external call failed; the tray resets to idle after the configured delay.
- `warning` and `paused`: reserved application states.

Presenter rendering, selection changes, popup close, and speaking-state cleanup must not emit API success or error. LLM and TTS workflows set `processing` immediately before the adapter call, `success` only after it returns, `error` when it raises, and `idle` when it is cancelled.

## Adapter ownership

- Core defines `ApplicationStatus` and the `StatusIndicator` port.
- The composition root injects the tray adapter into application/service workflows.
- The tray owns its pystray thread, icon lock, retry, reset timer, and stop cleanup.
- `memory_active` remains a separate API and defaults to false until a memory service is connected.

## Concurrency constraint

`StatusIndicator` is a single-operation projection for the current foreground-work model. Before concurrent external operations are supported, replace it with an operation-identity coordinator. Do not add feature-specific status precedence rules to presenters, providers, or adapters.

Tests must cover status color mapping, external-call lifecycle, timer reset, memory pixel differences, update retry, and stop cleanup.
