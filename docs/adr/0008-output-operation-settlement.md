# ADR-0008: Output operations have one settlement path

## Status

Accepted.

## Context

`OutputOperationCoordinator` exposed five terminal verbs while
`OutputOperationResult.__post_init__` already enforced the same kind/state
matrix. Runtime also owned interruption leases and manually released them at
eight sites. If `TaskSupervisor.submit()` raised, the operation stayed pending,
leaked its lease, and Escape could claim work that had never run.

## Decision

`settle(OutputOperationResult) -> bool` is the only terminal method. It rejects
pending, matches operation id + Workflow id + kind, removes the active record,
updates the tracker handle, releases the coordinator-owned interruption lease in
`finally`, and projects the acknowledgement. Stale settlement returns `False`
without touching handle or lease. `fail(intent, error)` remains the one helper
that creates user-facing failure policy.

`begin()` returns `None` and owns tracker handle and interruption lease with the
active record. `paste_outcome_result()` is the sole Paste outcome mapper.
Runtime uses one guarded begin-and-submit helper for ordinary output work. Paste
separately guards begin, admission, and submit; post-admission submit failure
uses `PasteOperationCoordinator.fail_to_start()` and one completion command.

## Measurements

The supplied reproduction was: submit raised `RuntimeError: task supervisor is
closed`, presenter states `['pending']`, leaked leases `['copy-op-1']`, and a
phantom copy interrupt. The regression now observes `['pending', 'failed']` and
no `copy-op-1` in the interruption plan. The focused suite reports 116 passing
tests in 0.64 s.

## Rejected alternatives

- Kind-specific terminal verbs duplicate the model's legal-state rule.
- Runtime-owned leases permit settlement and lease lifetime to diverge.
- Requiring every lease to have a worker is false for synchronous Paste reject
  paths.
- Changing shutdown ordering here mixes settlement with application lifetime.

## Consequences

- During command routing, a started output operation reaches a terminal
  acknowledgement and releases its lease.
- Tracker exceptions cannot orphan leases; stale settlement touches no owner.
- `OutputOperationResult.__post_init__` is the one kind/state validator.
- Shutdown-after-router-stop remains explicitly backlogged.
