# ADR-0009: Paste failures retain typed reasons and recover content safely

## Status

Accepted.

## Context

Four different target failures previously collapsed to the same user message,
and Paste failure semantics travelled as unstructured strings. A user could not
distinguish a missing target, a vanished window, refused activation, or focus
timeout. A pre-dispatch failure or cancellation also left the generated result
hard to recover manually.

The clipboard transaction cannot be blindly repeated after every non-success
state. `dispatched_unconfirmed` and `cleanup_failed` both mean that delivery may
already have occurred; preparing the text for another paste would encourage an
unobservable duplicate.

## Decision

`PasteFailureReason` is the closed set `no_target_observed`, `target_gone`,
`target_refused_focus`, `target_focus_timeout`, `target_changed`,
`modifiers_held`, `another_paste_active`, `clipboard_unavailable`, and
`unknown`. The detection boundary creates `PasteFailure(reason, message)`.
Callers propagate `reason` through `PasteOutcome` and
`OutputOperationResult`; they never recover semantics by comparing messages.

For terminal `failed` and `cancelled`, runtime obtains canonical text from the
active output-operation record and invokes the existing `OutputActions.copy()`.
The container wires that writer through its single
`ClipboardTransactionCoordinator`, so durable writes serialize with temporary
Paste ownership. `PasteOperationCoordinator` releases transaction and Paste
membership before it emits completion. The acknowledgement then tells the user
that manual Ctrl+V is available.

For `dispatched_unconfirmed` and `cleanup_failed`, runtime performs no fallback
copy and does not mutate the clipboard.

## Measurements

Before the change, four target conditions emitted the same “target not found”
message and zero typed reason values reached the acknowledgement. After the
change, nine of nine reasons have distinct messages and detection-path tests;
the focused Paste/clipboard/output/architecture suite reports 74 passing tests
in 1.73 s before the final full-suite verification.

## Rejected alternatives

- Parsing localized exception text would make semantics depend on wording and
  translation.
- Adding more Paste completion states would mix failure detail with dispatch
  truth and tempt callers to add a false `succeeded` claim.
- Copying after every terminal state could silently facilitate duplicate paste
  after an unconfirmed dispatch.
- Writing directly to the clipboard from runtime would create a second owner
  outside the container-scoped transaction coordinator.
- Adding Retry now would require separate eligibility and interaction policy;
  that product surface is backlogged.

## Consequences

- Diagnostics and UI receive stable failure semantics independently of text.
- Failed or cancelled Paste preserves recoverable canonical content only after
  temporary ownership has ended.
- Potentially delivered Paste never gets a convenience rewrite that encourages
  duplication.
- Durable Copy and temporary Paste writes are serialized by one clipboard
  owner.
- A future Retry control must be limited to failed/cancelled and preserve these
  dispatch-truth constraints.
