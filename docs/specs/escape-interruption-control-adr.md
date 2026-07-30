# ADR: Escape interruption control

## Decision

`Esc` is a progressive user-control gesture:

- Key down immediately interrupts the current control target.
- Holding the key for 0.5 seconds escalates to all content-producing operations.
- Releasing before the threshold prevents escalation.

`UserControlCoordinator` is the single owner of the semantic Focused Control
Surface and Current Interruptible Operation. It records only interruption
membership, ownership, and start order. It does not replace the authoritative
operation state owned by `WorkflowController`, provider configuration, speech,
or output-operation coordinators.

The platform adapter classifies the physical gesture. UI adapters report typed
surface focus lifecycle but do not choose cancellation scope. `AppRuntime`
executes the immutable interruption plan by routing exact operation identities
to their existing owners.

## Scope

Current interruption dismisses a focused surface and cancels work owned by that
surface. Without a focused ClipAI surface, it cancels the most recently started
interruptible operation.

Global interruption includes Workflow invocations, shortcut composition,
speech, copy, paste, and archive. It excludes provider configuration and user
persistence unless provider configuration belongs to the surface dismissed by
the initial current interruption.

Pinned and utility windows remain open during the global escalation. The
surface focused at initial key down has already followed the current-scope
dismissal rule.

## Lifecycle guarantees

Cancellation revokes an operation identity immediately and makes late
completion stale. Cooperative cancellation tokens and task cancellation stop
work where supported. An adapter already blocked in a synchronous external call
may return later, but its result cannot update state or UI.

Stopping does not emit Windows notifications. The Tray status projects the
remaining real operation lifecycles and returns to its baseline when none
remain.

## Consequences

Adding another interruptible operation requires registering one typed operation
lease and implementing identity-scoped cancellation in its owner. UI code must
not call provider, TTS, TaskSupervisor, or blanket cancellation APIs.
