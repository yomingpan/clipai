# ADR-0004: Paste Operation owns dispatch truth

## Status

Accepted.

## Context

Paste timing, cancellation, target dispatch, clipboard cleanup, and user-visible
completion were split across runtime, output actions, clipboard transactions,
and the Windows keyboard adapter. A keyboard event could already be dispatched
while a later cleanup exception projected the whole operation as failed, making
blind retry capable of duplicating content.

## Decision

One services-level Paste Operation module owns Paste identity, cooperative
cancellation, the irreversible Paste Dispatch point, at-most-once execution,
and the typed delivery and cleanup outcome. Runtime schedules the operation and
projects its outcome; it does not infer delivery from a worker return or a fixed
delay. ADR-0003 remains in force: the container-scoped
`ClipboardTransactionCoordinator` is the only owner of temporary clipboard
mutation and conditional restoration.

`PasteOperationCoordinator` is also the single owner of active membership and
terminal settlement. The application admits at most one Paste Operation across
the container. A concurrent request is rejected explicitly; it is not queued
and does not replace the active operation. `ResultOutputRuntimeModule` may keep
only the operation identity needed for scheduling and interruption. It must not
hold a concrete Paste handle or a parallel Paste registry.

Cancellation is an intent, not a terminal claim. A cancellation accepted before
worker execution settles immediately as `cancelled / not_dispatched`. Once
execution has started, the coordinator requests cooperative cancellation and
waits for clipboard cleanup and dispatch truth before emitting the terminal
outcome. The terminal outcome is emitted exactly once as
`PasteOperationCompleted` through the application command queue. `TaskSupervisor`
continues to own worker scheduling only; its task completion is not Paste
completion truth.

Clipboard Preservation is fail-closed. If the Windows adapter cannot safely
preserve every non-redundant original format, dispatch does not occur. A result
that was dispatched without target confirmation remains explicitly
`dispatched_unconfirmed`; cleanup failure never rewrites that fact as an ordinary
failure. Cancellation guarantees no delivery only before dispatch. Transient
paste content is excluded from Windows clipboard history and cloud clipboard;
an explicit Copy remains normal clipboard content.

## Consequences

- The Paste Operation interface is the test surface for cancellation, duplicate
  suppression, dispatch truth, and cleanup outcomes.
- The Workflow remains available after unconfirmed dispatch or cleanup failure,
  and the UI tells the user to confirm the target before trying again.
- Windows target and clipboard details remain behind platform adapters.
- A synthetic keyboard adapter cannot claim that the target application consumed
  clipboard content merely because input injection returned.
- Paste has no `succeeded` acknowledgement because target consumption cannot be
  observed. Its terminal acknowledgement is exactly one of `failed`,
  `cancelled`, `dispatched_unconfirmed`, or `cleanup_failed`.
