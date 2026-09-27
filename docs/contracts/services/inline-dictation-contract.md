# Inline Dictation contract

ADR-0019 is authoritative where it amends ADR-0018. Inline Dictation is one
non-Workflow interaction from the first accepted `Ctrl+Alt+M` press through
capture, delivery decision, optional refinement, Paste settlement, and a
terminal notice or explicit discard. `VoiceInputController` owns that semantic
lifetime. Capture, provider invocation, Paste Operation, and view leases retain
separate identities. Runtime routes typed effects and matching acknowledgements;
it does not create another interaction registry.
Capture ID and Inline Interaction ID have distinct generated values. The existing
diagnostics log records content-free, monotonic lifecycle stages keyed by these
IDs and the provider/Paste operation IDs. A requested UI presentation is not
evidence that its first frame was visible, and Paste Dispatch is not insertion.

## User journeys

| Mode and intent | Observable journey | Required outcome |
| --- | --- | --- |
| Choice-based (default), two presses | Freeze the external target on the first press; the second press stops recognition; show complete recognized text with Paste raw, Refine, and Discard. | No provider call or Paste before the explicit choice. |
| Minimal input, short then short | Freeze target, listen, stop, then request raw Paste once usable canonical text exists. | Show a compact non-activating status and no choice window in the normal path. |
| Minimal input, short then long | Freeze target, listen, stop, then request refinement and Paste once usable text exists. | The hotkey boundary emits one long stop intent; release cannot emit a second short stop. |
| Mode change during capture | Save the selected mode through a typed tray command. | A failed save changes nothing; a successful save affects only later interactions. |
| No speech or recognition failure | Stop or timeout without usable canonical text. | No Paste; show a truthful retryable failure. Preserved recognized text remains recoverable when available. |
| Refinement unavailable, failed, or empty | Preserve the original text and show complete text in recovery. | Offer explicit Paste raw, Copy, or Discard. Never silently Paste the original. |
| Frozen target invalid or focus refused | Reject the Paste attempt without selecting a new foreground target. | Keep complete text and Copy/manual-paste guidance visible. |
| Esc during capture, refinement, or Paste | Cancel only the matching operation. | After discard, no new Paste admission; wait for provider cancellation admission or Paste settlement before allowing a new capture. Dispatch cannot be undone. |
| Paste terminal acknowledgement | Route the matching Paste Operation outcome to the controller. | `dispatched_unconfirmed` says the shortcut was sent and asks the user to check the original field; `failed`, `cancelled`, and `cleanup_failed` show their distinct recovery and cleanup truth. Never claim insertion success. |

The choice window and status/recovery surface may only close under the current
interaction and view lease. A late provider result, Paste acknowledgement, or
terminal dwell callback from an older interaction cannot change or close a
newer one. A second shortcut during refinement or pending Paste is rejected
with visible feedback. A new capture is admitted only after the preceding
interaction reaches a settled, dismissible terminal phase.
View Confirm, Copy, and Esc callbacks carry the interaction ID captured when
their window was created. The controller rejects a callback from an older
window even if a newer Inline interaction is now in a compatible phase.
Choice, cancellation, and discard presentation effects carry the same frozen
interaction ID; presenters compare it with the active view lease before
changing or closing a window.
During capture cancellation, the status remains visible as cancelling until
the matching engine terminal event or six-second watchdog settles it. A normal
cancel closes without a failure flash; a watchdog timeout reports the missing
acknowledgement before closing.
Capture failures without recoverable text show a three-second terminal notice
with inactive status before the view closes; the previous listening or
finalizing label must not remain active during that notice. Starting a newer
interaction retires that older notice immediately so it cannot cover the new
status view; any late close request remains scoped to the older view lease.

The engine promotes its last interim segment once on stop and discards it on
cancel. The 120-second listening limit begins only on the matching Listening
event. The six-second stop/cancel watchdog produces a retryable timeout, never
a fabricated success. No provider call or Paste follows from opening,
rendering, focusing, or closing a view.

`ProviderExecutionModule` owns the provider task and cancellation admission;
`PasteOperationCoordinator` owns dispatch, cancellation, and terminal truth;
`ClipboardTransactionCoordinator` owns temporary clipboard preservation.
Esc before Paste Dispatch requests cancellation and restoration through these
owners. After dispatch, report only `dispatched_unconfirmed` or the actual
cleanup failure; do not retry automatically.
If provider cancellation has not settled after six seconds, the matching
interaction shows an unconfirmed cancellation state with complete original
text and Copy. Esc may retry the same provider operation cancellation. A new
capture remains blocked until a matching cancellation admission or provider
settlement; the timeout alone does not count as acknowledgement or permit Paste.
