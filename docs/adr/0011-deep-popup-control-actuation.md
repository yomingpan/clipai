# ADR-0011: Deep Popup control owns actuation

## Status

Accepted.

## Context

Popup focus, visibility, output feedback, attention, command reporting, and
scheduled checks shared one transition table, but the presenter interpreted and
executed its action tuples. That exposed focus generations and operation policy
to a broad rendering module, duplicated toolkit mechanics, and made each new
Popup control behavior require coordinated Presenter changes.

## Decision

Each live Workflow view has one `PopupControl`. Its public interface accepts
semantic focus lifecycle observations, output begin and settlement, attention,
projection context updates, and disposal. It exposes only the read-only
`focused_inside` and `owns_focus` projections needed for shortcut and owned-dialog
routing.

`PopupControl` owns focus evidence sampling, focus generations, bounded 25 ms
confirmation retries, outside-focus scheduling, UI output-operation identities,
Paste visibility policy, attention deferral, feedback actuation, control-surface
command reporting, and close requests. Its transition state and action types are
private UI implementation details.

`ResultDialogPresenter` owns Workflow-view membership, dead-view detection,
canonical text and selection routing, snapshot rendering, and close-request
deduplication. It routes toolkit events to `PopupControl`; it does not interpret
focus or output transition actions.

All delayed control work uses the view's `DialogLifecycle`. Eviction and runtime
shutdown dispose the control. Disposed controls suppress late callbacks and all
subsequent side effects.

The dialog and surface remain mechanical adapters: they apply visibility,
focus, flash, enabled-state, pulse, message, overflow, and focus-projection
requests without owning policy.

## Consequences

- Adding a Popup control behavior has one semantic interface and one actuation
  owner instead of a Presenter branch plus a transition branch.
- Native and toolkit focus evidence cannot be asserted by Presenter callers.
- Output and focus identities remain private and cannot leak into snapshots.
- Presenter tests cover wiring and rendering; `PopupControl` tests cover
  lifecycle policy through observable commands and adapter calls.
- A private state seam remains replaceable without changing Presenter or widget
  contracts.

## Rejected alternatives

- Keeping action tuples public preserves the original shallow-module coupling.
- Moving policy into widgets would mix toolkit rendering with operation state.
- Letting the control own view membership or canonical content would merge
  rendering lifetime with actuation lifetime.
- Using the root timer directly would bypass per-dialog lifecycle cleanup.
