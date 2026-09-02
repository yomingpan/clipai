# Popup Surface Deepening Plan

Status: implemented from baseline `c70d08d484ea7599face7e0afdfd37fcf5a2c44a`

## Purpose

Deepen the Popup presentation module without changing Workflow, provider,
clipboard, paste or output-operation ownership. The work ends at a single
widget projection seam; it does not split the presenter/router or create a new
state owner.

The same delivery also removes two Entry Panel lifecycle ambiguities that made
the shared primary surface visibly unstable: Esc versus Back, and capability
availability versus input preparation.

## Fixed owners

- `WorkflowController` remains the only owner of Workflow execution snapshot,
  active invocation, cancellation, accepted history and feedback projection.
- `WorkflowRuntimeModule` remains the only owner of Workflow membership,
  semantic Foreground Workflow and visible/headless lifetime.
- `ProviderExecutionModule`, `ClipboardTransactionCoordinator` and
  `PasteOperationCoordinator` are unchanged.
- `PopupControl` remains the only per-Workflow owner of output-operation
  identity, in-flight enable state, acknowledgement pulse and stale settlement.
- `EntryPanelRuntimeModule` owns Panel lifecycle and preparation identity;
  `EntryPanelCoordinator` owns pure navigation and option projection.
- `PrimarySurfaceHost` remains the only mounted-view replace/rollback owner.

## Problem statement

Before deepening, `ResultDialogPresenter._apply` knew widget setters, feedback
eligibility, first-use guidance, baseline action callbacks and speaker state.
Those concerns were diffed directly from `SessionSnapshot`, while content and
operation acknowledgement used different paths. The result worked, but every
new Popup field increased presenter knowledge and made it easy for a snapshot
render to overwrite operation state.

The Entry Panel had two related projection problems:

1. `EntryPanelEscape` meant Back on non-root pages and Close at root, so Esc did
   not provide the immediate global brake promised by product philosophy.
2. Preparation was represented as disabled Actions with an error-like reason.
   Lifecycle-only option changes participated in the body render key, causing
   widget replacement at open and settlement.

## Target interfaces

### Pure Popup projector

`ClipAI.core.popup_presentation` exposes:

```python
project_popup_presentation(
    snapshot: SessionSnapshot,
    *,
    guidance_already_shown: bool = False,
) -> PopupPresentationModel
```

The returned frozen model contains exactly the widget-neutral state needed by
the non-content surface:

- title, model and source preview;
- pinned and Back availability;
- Action contract and input source;
- caller-authorized guidance visibility;
- baseline enabled actions;
- speaking state;
- optional valid feedback projection.

Canonical content, editable Voice Draft content, presentation documents,
incremental append and flash are excluded. They retain their existing paths and
identities.

Projection rules are fail-closed:

- feedback requires `COMPLETED`, a feedback contract and a valid displayed
  step;
- guidance requires `COMPLETED`, the snapshot flag and caller-supplied unseen
  state;
- `CONTEXT_QUESTION` excludes `follow_up` from baseline actions;
- no projector rule reads Tk, focus, visibility or an operation acknowledgement.

### Popup render seam

`BaseResultSurface.render(model)` is the only projection seam for these fields.
It retains the last model and diffs five field groups:

1. header: title/model/source/pin/Back/contract/input source;
2. baseline actions;
3. speaking;
4. feedback;
5. guidance edge.

Workflow callbacks are bound once when the view is created. The feedback
callback reads `view.step_id` when the user submits, so navigation cannot send
feedback to a step captured by the first render.

`StandardResultActions` combines three facts before configuring button state:

```text
callback exists AND baseline available AND PopupControl operation gate enabled
```

Changing baseline availability therefore cannot release an in-flight disable.
Only `PopupControl` settles that gate and owns pulse/error actuation.

## Entry Panel lifecycle

### Close and Back

- `EntryPanelBack` replaces the ambiguous `EntryPanelEscape` command.
- Esc and the right neutral header control always emit `CloseEntryPanel`.
- Esc closes root, scene or More immediately and cancels matching preparation.
- The non-root left Back control and `Ctrl+Z` emit `EntryPanelBack`.
- Back moves More → scene → root. At root it is a no-op.
- Back never closes and preserves lifecycle ID, source preview, density,
  navigation state, pending/error status and frozen input.

### Pending versus disabled

`EntryPanelOption.pending` is an immutable lifecycle projection independent of
`enabled` and `disabled_reason`.

- During preparation, an otherwise-capable option remains `enabled=True` and
  becomes `pending=True`.
- A real policy or input incompatibility wins: `enabled=False`,
  `pending=False`, authoritative `disabled_reason`.
- Coordinator numeric resolution, UI mouse/keyboard intent and the final app
  admission guard all reject pending invocation.
- Pending uses neutral loading copy. Red is reserved for a real disabled reason.

### Stable card topology

`_body_render_key` includes page/category/density/search and option topology
plus static detail visible at the selected density. It excludes
`enabled/pending/disabled_reason`.

Each card owns an in-place updater whose mutable closure points at the latest
immutable option. Hover, focus and click callbacks read that latest value.
Opening, completion, failure and availability refresh do not rebuild the body;
only topology or static visible detail changes do.

## Delivery slices

### M0 — Characterize before production change

- lock header/actions/feedback/guidance/speaking field groups;
- lock per-Workflow highest-revision mailbox coalescing;
- lock completed-only guidance de-duplication;
- lock primary replacement ordering: success closes Panel, failure retains it.

The characterization suite must pass against untouched baseline production and
must not be relaxed during later slices.

### M1 — Pure model and render seam

- add projector tests first;
- add architecture AST gate proving core-only/Tk-free imports;
- add `BaseResultSurface.render(model)` field-group tests;
- separate baseline Action availability from the PopupControl operation gate;
- bind callbacks once and use live step feedback submission;
- retain content/flash and presenter/router structure.

### M2 — Entry Panel navigation and card lifecycle

- rename typed Back intent across core/UI/app;
- route Esc directly to runtime close/cleanup;
- add pending projection and precedence tests;
- update cards in place and prove latest-option callbacks;
- update contracts, specifications, testing guidance and Windows smoke rows.

## Verification gates

Automated gates:

- targeted core, service, app and UI tests for both slices;
- all architecture tests, including projector dependency ownership;
- full non-integration unit suite;
- integration-marked smoke suite in the configured environment;
- compile check for `ClipAI`, scripts and tests.

Manual Windows evidence remains required for compositor-visible continuity,
mixed DPI, IME and native focus. A fake host can prove replace ordering and
rollback contracts, but cannot prove absence of an opaque native frame.

## Review triggers

Revisit this seam only if one of these becomes true:

- a second surface needs the complete Popup model;
- content rendering must participate in the same atomic model transaction;
- another owner attempts to project output-operation enable/pulse;
- a second Entry Panel card implementation appears;
- primary replacement failure needs app-level retry or user recovery beyond
  retaining the mounted Panel.

None of these triggers authorizes a second state owner, Tk root, event bus,
provider task registry, clipboard transaction path or Paste membership table.
