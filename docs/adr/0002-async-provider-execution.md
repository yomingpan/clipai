# ADR-0002: Async provider execution and streaming settlement

## Status

Accepted.

## Context

Provider HTTP previously ran as blocking `requests` work in the shared blocking-work pool. Cancelling a running `Future` could not close its connection, stale invocations retained capacity, and the parsed `stream` setting was lost while resolving an Action.

## Decision

`ProviderExecutionModule` is the single owner of provider network tasks. It owns one long-lived asyncio loop thread and one shared `httpx.AsyncClient` transport. An operation identity maps to exactly one asyncio task until settlement; cancellation calls `task.cancel()` and releases the identity only after the task settles.

All provider adapters and model-catalog validation use the same async transport. Their common contract is an async stream of `LLMTextDelta` followed by exactly one `LLMCompleted`; typed provider exceptions remain the error channel. Raw deltas are coalesced for at most 40 ms and terminal events flush immediately.

Provider completion may await downstream coordination, but it must not execute blocking side effects on the provider loop. Generated-result TTS is submitted to the `TaskSupervisor` media lane and retains its own cancellation hook and operation identity.

Streaming remains disabled by default. `app.stream` is the catalog default and an Action may explicitly override it. Partial failures retain canonical partial text, do not create a successful Workflow step, and expose Copy only.

## Consequences

- Provider cancellation closes in-flight async response work instead of waiting for a blocking timeout.
- Provider networking no longer consumes `TaskSupervisor` capacity.
- The shared client provides connection pooling and is closed during runtime shutdown.
- Incremental content stays plain text; formal presentation transformation happens only after completion.
