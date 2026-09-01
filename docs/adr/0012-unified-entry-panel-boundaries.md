# ADR-0012: Unified Entry Panel is a bounded entry surface

## Status

Accepted.

## Context

ClipAI needs a cursor-adjacent launcher for recent Actions and configurable
flagship scenes. The existing hotkey listener already owns physical key timing,
`WorkflowRuntimeModule` owns Workflow admission, `WorkflowController` owns
successful steps, and `PopupControl` owns per-Workflow Popup actuation. Putting
the launcher inside any of those owners would add unrelated state and duplicate
focus, clipboard or execution policy.

External Action input also cannot be prepared by the widget. The Panel owns
foreground while visible, so restoring the captured external target and reading
selection are blocking, identity-scoped work that may complete after the Panel
has closed or reopened.

## Decision

- `EntryPanelCoordinator` owns immutable entry navigation, the active density,
  search, disabled projection and numeric resolution. It is toolkit-free; its
  initial density comes from the existing persisted user-preferences owner.
- `EntryPanelRuntimeModule` owns Panel membership, launch/source identity and
  one active input-preparation identity. Only matching completion can request
  Workflow admission. A second Action intent while preparation is active is
  ignored rather than replacing that identity.
- `UnifiedEntryPanelDialog` is an independent UI adapter on the existing Tk root.
  It renders projections and emits typed intents; it does not call services,
  platform adapters or providers.
- Accepted Action admission returns the authoritative Workflow identity.
  `EntryPanelRuntimeModule` uses that identity with the Panel lifecycle identity
  to request one explicit visual handoff; UI never infers a handoff from focus,
  closure, cursor movement or an unrelated Workflow snapshot.
- `ResultDialogPresenter` owns only the cross-surface actuation of that handoff:
  capture the Panel's actual outer bounds, build a new Popup while withdrawn,
  hide the Panel, reveal the Popup, then destroy the Panel in the same UI turn.
  If reveal fails, it restores the same Panel for retry. Reused Popups keep their
  existing bounds. Bounds use physical screen position and toolkit-logical size;
  navigation and Workflow/Popup state ownership do not move. Its private
  `EntryPanelPopupHandoff` deep module owns the handoff implementation state and
  ordered commit/rollback interface; this does not create another presentation
  owner.
- The platform hotkey listener owns the exact `Alt` 500 ms hold and digit
  claim. Alt auto-repeat remains part of the same physical hold. Runtime settles
  the consumed hold by identity when the Panel lifecycle ends, so a missed OS
  release cannot block the next real hold. The listener emits typed facts and
  never resolves Action IDs.
- External target validation/activation remains a platform capability behind an
  opaque core port. Selection capture reuses `InputResolver` and the one
  `ClipboardTransactionCoordinator`.
- `WorkflowRuntimeModule.start_action` is the only Action admission seam for
  both legacy shortcuts and the Panel.
- `WorkflowController` emits a minimal accepted-step identity only after it
  accepts the active invocation. `RecentActionHistory` owns unique top-three
  Action references; its platform store persists only Action ID and press type.
- Categories, ordering and candidate `action_id + press_type` references are
  loaded from `config/entry_panel.yaml`. Candidate Action `label/description`
  are joined from the already compiled active Action Language Pack during app
  composition. Execution semantics remain in `ActionCatalog`; coordinator and
  UI do not inspect locale or pack identity.

## Enforced boundaries

- No second Tk root, action executor, input resolver, clipboard coordinator,
  provider registry, event bus, recent aggregate or Popup control.
- Panel lifecycle, selection preparation, Workflow, provider invocation,
  successful step, output operation and view lifecycle use distinct identities.
- Late preparation completion cannot start an Action, close a newer Panel or
  replace its feedback.
- UI and config do not infer provider, Personal Style, voice or input viability.
  Known availability comes from authoritative runtime owners; execution-only
  viability is reported by the real Action lifecycle.
- Boundary docs and AST/import tests change with the modules they constrain.

## Alternatives rejected

- Extending `PopupControl` merges entry navigation with Workflow actuation.
- Closing the Panel before the identity-matched Popup is fully built creates a
  visible gap; revealing both surfaces creates a double flash; caching unscoped
  "last Panel bounds" can move a later unrelated Popup and is therefore rejected.
- Calling `ActionExecutor` from UI bypasses Workflow admission and cancellation.
- Registering modifier-only `Alt` as an ordinary shortcut conflicts with
  trigger-token and direct digit semantics.
- Deriving recents from snapshots or provider completion reports success too
  early and uses the wrong identity.
- A second Tk root or WebView creates another focus and lifecycle owner.

## Consequences and review triggers

Implementation requires contracts and tests before visible UI, but it can be
rolled back behind one feature flag without changing direct shortcuts. Review
this decision if a second non-Panel consumer needs entry navigation, if another
feature needs persisted recent content instead of Action references, if sorting
becomes a persisted preference, or if external activation remains unreliable
after real Windows measurements.
