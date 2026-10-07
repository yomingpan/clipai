# ADR-0019: Inline Dictation remains one interaction through Paste settlement

Status: accepted design, implementation in progress. Amends ADR-0018's choice,
fallback, and window-settlement rules.

## Context and decision

Inline Dictation is a non-Workflow interaction. Today its capture and pending
choice belong to `VoiceInputController`, but confirmation clears the choice
before refinement or Paste settles. A second capture can then start while the
first window still shows refinement. Esc no longer finds an inline interaction
to cancel, and a late provider callback can still request Paste.

`VoiceInputController` remains the single owner of the interaction's semantic
lifetime: capture, delivery decision, refinement, Paste pending, terminal notice, and
discard. App runtime routes its typed effects and identity-matched provider and
Paste acknowledgements. `ProviderExecutionModule` continues to own provider
tasks, and `PasteOperationCoordinator` continues to own Paste membership,
cancellation intent, dispatch truth, and cleanup. Capture, provider invocation,
Paste Operation, and view lifecycle identities remain distinct; acknowledgements
must carry enough typed identity to reject late results.

## Product interaction modes

The tray offers **Choice-based** (the current interaction and initial default)
and **Minimal input** as explicit Inline Input Modes. A mode change becomes
active only after its setting is saved successfully and affects only later interactions;
the controller captures the selected mode with the Inline Interaction ID at the
first accepted shortcut. Tray commands request the mode change through the
typed runtime path; the tray and window do not own admission or operation state.

Both modes use `Ctrl+Alt+M` to start capture and freeze the external target.
In Choice-based mode, the next press stops capture and then presents the raw,
refine, and discard choices. In Minimal input mode, a short second press stops
capture and explicitly requests raw delivery; a long second press stops capture
and explicitly requests refinement followed by delivery. Long-press intent is
recognized once by the hotkey boundary and passed as a typed stop intent; its
release cannot also emit a short stop. The gesture is not
inferred from window visibility or a timer in the controller. No Paste request
is admitted until recognition yields usable canonical text. If recognition
fails or yields no usable text, no Paste is attempted.

Minimal input keeps the user in the original text field. Its normal path uses
a compact, non-activating status surface for preparing, listening, finalizing,
refining, Paste pending, and the terminal receipt; it does not open a choice
window. The status may say `Listening` or `Refining` only after the respective
owner reports that state. Failure opens an actionable recovery surface with
the complete recognized text when available. A target that changed or cannot
be safely activated never becomes the current foreground target by default;
the user can Copy the text and paste manually. The destination should be
identifiable without storing or exposing a raw window title in diagnostics.
If the frozen target becomes invalid, there is no automatic retarget or Paste.

## Interaction, cancellation, and output contracts

Each Inline Dictation receives an opaque Inline Interaction ID at the first
accepted shortcut. It is neither a Workflow ID nor an output-operation ID.
Capture, provider invocation, Paste Operation, and view lifecycle retain their
own identities and link back to that interaction only through a typed Inline
origin. `WorkflowOrigin(workflow_id)` and `InlineOrigin(interaction_id)` are
the two legal output origins. `OutputOperationIntent`, `PasteRequest`, and
terminal acknowledgement routing must carry the origin envelope; runtime must
not manufacture a Workflow-shaped ID for Inline Dictation.

`VoiceInputController` owns exactly these externally observable Inline phases:

| Phase | Legal user intent | Admission and settlement rule |
| --- | --- | --- |
| `capturing` | Stop or discard | A second shortcut requests stop with a typed raw/refine gesture in Minimal input; Choice-based mode defers that choice. Esc requests capture cancellation. |
| `choice` | Paste raw, refine, or discard as available | Choice-based mode uses this phase after recognition; Minimal input enters it only for recovery after a failed refinement, where raw paste, Copy, or discard are offered without a second refinement invocation. No new capture; raw admits Paste, Esc discards. |
| `refining` | Discard | A second shortcut is rejected with visible feedback. Esc records discard intent and requests provider cancellation. |
| `refine_cancellation_requested` | Wait | No new capture until the provider owner acknowledges identity-scoped cancellation admission and the controller has quarantined later results. Transport settlement may follow later; success, failure, and late result are ignored for delivery. |
| `paste_admitted` | Discard where dispatch has not occurred | A second shortcut is rejected. Esc is forwarded as typed Paste cancellation intent. |
| `dispatched` | Acknowledge terminal notice | Esc cannot promise undo and must preserve `dispatched_unconfirmed` truth. |
| `terminal_visible` | Start a new capture or dismiss | A new capture is allowed after the prior operation has settled; any old notice dismissal or close callback is scoped to its old interaction and view lease. |

Provider cancellation is not inferred from a local cancellation token. The
provider module emits an identity-matched typed acknowledgement that it has
accepted cancellation and will not admit that invocation's result for delivery;
transport cleanup may finish later. Runtime routes the acknowledgement to the
controller, which alone decides when a new capture is permitted. Waiting for
this acknowledgement has a bounded deadline and truthful visible pending or
failure feedback; a transport timeout is not silently treated as an
acknowledgement. A provider error preserves raw text for explicit recovery;
explicit discard and provider cancellation never invoke fallback Paste. A
provider completion after discard is observable for diagnostics but cannot
cause a Paste request.

The app routes identity-matched provider and Paste terminal acknowledgements to
`VoiceInputController`; the controller maps them to presentation and next legal
intent. `PasteOperationCoordinator` remains the only owner of dispatch and
clipboard cleanup truth. This is a routing contract, not a second registry in
runtime or the UI.

Esc during refinement is an explicit discard. It requests provider cancellation
and prevents any later callback from requesting Paste. A new capture may start
after the matching cancellation-admission acknowledgement and result quarantine;
transport cleanup may finish later.
`Ctrl+Alt+M` rejects a second capture with visible feedback while refinement or
Paste is active. The inline window stays visible with truthful pending state
until the Paste Operation reaches a terminal acknowledgement.

Esc after Paste admission but before Paste Dispatch cancels and discards that
interaction. Its temporary clipboard transaction must restore the prior
clipboard content or report `cleanup_failed` if restoration cannot be proved;
it must not copy dictated text as a cancellation fallback. After
Paste Dispatch, cancellation cannot promise to undo delivery, and the
acknowledgement must retain `dispatched_unconfirmed` truth. This
explicit-discard exception must be represented as typed cancellation intent in
the existing Paste owner, not as a second cancellation registry.

Provider unavailability or refinement failure preserves the original recognized
text and requires a fresh explicit raw-paste, Copy, or discard intent. An ordinary
Paste failure before dispatch preserves complete text in the recovery surface
and offers an explicit Copy action. Clipboard mutation requires that typed user
intent; failure alone must not replace the user's clipboard. The first release
offers Copy and manual paste recovery, not automatic retry; any future retry needs a new Paste Operation
identity and proof that the previous attempt was never dispatched.
`cleanup_failed` adds no fallback clipboard write and keeps a warning visible
about uncertain restoration. `dispatched_unconfirmed` displays a readable
notice telling the user to check the original target, then closes only after
a tested dwell interval. None of these states claims confirmed Paste success.

## Product result contract

Every terminal or recovery state presents both truthful delivery status and a
plain next step. The inline window remains available whenever the user needs it
to recover content; it does not disappear merely because an internal task ended.

| Actual outcome | User-facing promise | Available recovery |
| --- | --- | --- |
| `dispatched_unconfirmed` | The paste shortcut was sent; confirm the original text field. | Readable terminal notice, then identity-scoped close. Do not call this success or automatically retry. |
| Failure before dispatch or focus activation | Nothing was pasted; recognized text is still available. | Keep recovery visible and offer Copy with manual paste guidance. |
| Explicit discard | Cancelled; nothing will be pasted. | End the interaction and allow a new capture after cancellation is accepted. |
| Refinement error or provider unavailable | Text could not be refined; the recognized original remains available. | Explicitly offer raw paste, Copy, or discard; do not silently paste it. |
| `cleanup_failed` | Delivery or clipboard restoration could not be fully confirmed. | Keep warning and content visible; do not overwrite clipboard as a convenience fallback. |

For every failure before Paste Dispatch, the user can recover the complete
recognized content without speaking again unless recognition produced no usable
text. Recovery and manual paste must never combine
to create a duplicate delivery risk.

The old terminal notice and its timer may dismiss only the view lease belonging
to the old Inline Interaction ID. Starting a new interaction cannot let an old
close callback hide its status. A discarded or failed interaction retains its
recognized text until the user has an explicit recovery or dismissal path.

## Considered options

- Close the window when refinement settles: rejected because Paste is still
  pending and a non-Workflow output acknowledgement has no Popup to render it.
- Allow a second capture during refinement: rejected because the one inline
  window and current admission rules cannot represent two live interactions.
- Let Esc cancel refinement but Paste the original text: rejected because an
  explicit discard must not create an external side effect.
- Add a second runtime registry for inline work: rejected because it would
  duplicate lifecycle state owned by `VoiceInputController`.

## Consequences and review trigger

Inline acknowledgements need a typed route to the controller and inline view.
The current `workflow_id` field that carries an inline capture ID must be
replaced by the typed Inline origin contract as part of the migration. Review
this decision if the product requires concurrent inline captures or a second
visible inline surface.
