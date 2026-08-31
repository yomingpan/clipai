# Unified Entry Panel — System Design

Status: proposed architecture plan  
Scope: an independent, desktop-native action-entry UI that reuses ClipAI's
existing workflow and service pipeline. This document intentionally contains no
implementation change.

The implementation sequence, commit boundaries and documentation gates live in
[the development plan](./unified-entry-panel-development-plan.md).

## Executive decision

Adopt a **bounded Entry Panel slice**, not a rewrite and not a PopupControl
extension. The panel is a separate UI surface, but it sends typed intent into
the existing application runtime. It does not own provider work, clipboard
transactions, workflow state, or physical keyboard state.

This is a Yellow architecture diagnosis: the existing system already has the
right execution capabilities, but hotkeys and UI are active change hot spots.
A focused seam now prevents the next entry surface, category, or focus feature
from adding more special cases to `PopupControl`, `ResultDialogPresenter`, or
the hotkey listener.

The selected design preserves these current owners:

| Capability | Authoritative owner | Entry Panel responsibility |
|---|---|---|
| Workflow snapshot, active invocation, cancellation, accepted successful steps | `WorkflowController` | Project state only; never infer success from it. |
| Workflow membership, foreground/lifetime, provider binding | `WorkflowRuntimeModule` | Request typed start admission only. |
| Provider task, transport cancellation and settlement | `ProviderExecutionModule` | None. |
| Selection and paste clipboard transactions | Container-scoped `ClipboardTransactionCoordinator` | None; request existing capture through the action path. |
| Physical key state, hold timer and stale recovery | Platform hotkey listener | Add a generic modifier-hold gesture. |
| Panel launch/source/selection-operation identity | `EntryPanelRuntimeModule` | Project one active Panel and reject stale preparation completions. |
| Panel navigation, search, density and numeric resolution | `EntryPanelCoordinator` | Apply pure transitions; never execute an Action. |
| Recent successful Action aggregate | `RecentActionHistory` | Project the top three references; never infer success. |
| Dialog/toolkit lifecycle, focus and geometry | UI adapter | Own the Panel surface only. |

## Evidence and current capability

The recommendation is based on the current repository, not a proposed parallel
stack.

- The established action path is `StartAction` → `WorkflowRuntimeModule` →
  `ActionCatalog` → `ActionExecutor` → `InputResolver` →
  `ProviderExecutionModule` → result routing → `WorkflowController.complete`.
- All 27 PRD canonical action IDs already exist in the current Action catalog.
  The missing capability is a presentational catalog: category/order/copy and
  safe enumeration, not a new action execution mechanism.
- `ResultDialogPresenter` already owns a single hidden CustomTkinter root and
  its main loop. A second root or WebView would create competing lifecycle and
  focus ownership.
- `InputResolver` already prefers selection then clipboard, and its selection
  capture is protected by the single clipboard transaction coordinator.
- The existing hotkey implementation is deliberately stateful and hardened
  around timer identity, release semantics, stale physical-state recovery and
  shutdown. A modifier-only `Ctrl+Alt` is not a normal shortcut binding.
- Only an immutable successful step accepted by `WorkflowController.complete`
  is a valid signal for recent actions. Provider completion, operation-tracker
  success, view visibility and snapshot revisions are all too early or too
  ambiguous.

Key source material:

- [Product requirements](./unified-entry-panel-product-requirements.md)
- [Architecture boundaries](../ARCHITECTURE_BOUNDARIES.md)
- [Product philosophy](../Product_philosophy.md)
- [Testing strategy](../TESTING_STRATEGY.md)
- `ClipAI/platform/hotkey.py`
- `ClipAI/app/runtime_workflows.py`
- `ClipAI/services/execute_action.py`
- `ClipAI/services/workflow_controller.py`
- `ClipAI/ui/result_dialog.py`

## Design principles and non-goals

### Principles

1. A new entry UI may be independent; execution must remain a single reusable
   pipeline.
2. Every side effect starts from a typed user intent. Opening, focusing,
   navigating, rendering and provider completion never imply a new action.
3. Input is captured at action intent, not at panel open. This preserves the
   existing "explicit selection first, clipboard fallback" rule.
4. The panel closes only after input preparation has settled and the workflow
   runtime admits the action. UI feedback mirrors the actual lifecycle:
   preparing, rejected, disabled or closed.
5. A lightweight abstraction is added only where it removes present coupling:
   modifier hold, entry IA/catalog, action admission, external-target
   activation and recent-action history.

### Non-goals

- No WebView, second Tk root, global EventBus, UI-to-provider call, or parallel
  clipboard/focus restoration mechanism.
- No rewrite of actions, workflows, providers, result popups or direct
  shortcuts.
- No cross-device sync, user-configurable sorting, analytics profile, or saved
  input/output history in the first release.
- No pre-flight clipboard probe. Input/OCR availability that is only knowable
  at execution remains an execution-time result.

## Target architecture

```text
physical Ctrl+Alt hold
        │  (platform owns physical state, timer, key claim)
        ▼
OpenUnifiedEntryPanel typed command
        ▼
EntryPanelRuntimeModule ──────── EntryPanelCatalog ← config/entry_panel.yaml
  │ launch/source/selection identity              (IA/category copy/Action refs)
  │                                      ← active Action Language Pack
  │                                         (candidate label/description)
  ├── EntryPanelCoordinator (pure navigation/search/density transitions)
  │ external target restore + action-time capture, scoped by selection ID
  ▼
WorkflowRuntimeModule.start_action(...) → ActionExecutor → InputResolver
                                                │              │
                                                │              └─ existing ClipboardTransactionCoordinator
                                                ▼
                                      ProviderExecutionModule
                                                ▼
                                      WorkflowController.complete
                                                │ accepted immutable WorkflowStep only
                                                ▼
                                      RecentActionHistory → atomic JSON store

UnifiedEntryPanelDialog
  └─ shared Tk root; projects state; emits typed select/close/search intents
```

### New bounded components

| Component | Layer | Responsibility | Must not own |
|---|---|---|---|
| Generic modifier-hold gesture | platform + typed core command | Exact Ctrl+Alt recognition, 1.5 second timer, physical-state recheck and numeric-key claim. | Panel UI, action execution, clipboard. |
| `EntryPanelRuntimeModule` | app | Compose launch lifecycle, source snapshot, panel coordinator and action admission. | Workflow state, provider task, raw native UI handles. |
| `EntryPanelCoordinator` | services | Own the immutable Panel projection and pure navigation, search, density, disabled-state and numeric-key transitions. | Toolkit state, external focus, Action execution or persistence. |
| `UnifiedEntryPanelDialog` | ui | Render/filter/navigate; native placement/focus; emit typed UI commands. | Services, platform APIs, clipboard, provider. |
| `EntryPanelCatalog` | services/config composition | Validated panel IA: category, order, copy, flagship selection. | Action execution semantics or prompts. |
| `ExternalWindowRef` + activator port | core/platform | Opaque external target reference and safe restore/validate operation. | Panel policy or duplicate paste ownership. |
| `RecentActionHistory` + store | services/platform persistence | Top-three replay references from accepted steps; non-blocking durable write. | Workflow history, preferences or analytics. |

## Minimal changes by seam

### 1. Modifier-hold hotkey, not a normal shortcut

Extend the platform listener with a reusable `modifier_hold` gesture contract
for the exact physical `Ctrl+Alt` chord. Do **not** add `ctrl+alt` as an
ordinary `ShortcutCatalog` binding: ordinary bindings expect a trigger token;
modifier-only release and digit input would otherwise race the existing short
press/direct shortcut paths.

Required behavior:

1. Both modifiers down creates a press identity and starts the 1.5 second timer.
2. Releasing either modifier before the deadline cancels; there is no short
   invoke.
3. A non-modifier before the deadline cancels only the entry candidate; normal
   direct shortcuts retain their existing behavior.
4. At the deadline, recheck the same press identity and actual physical state.
   Only then emit `OpenUnifiedEntryPanel`.
5. Once opened with modifiers still held, the platform claims top-row digits
   and numpad digits for the Panel until the chord is released. This prevents a
   competing direct shortcut.
6. Stale recovery and shutdown are identity-scoped. Repeated Ctrl+Alt while a
   Panel is open raises the existing Panel; it does not reset/capture a new
   source.

The existing Keyboard Shortcut guide receives the long `Ctrl+Alt` description;
the Panel itself does not show an extra shortcut-guide entry.

### 2. Action catalog versus entry catalog

Keep `ActionCatalog` execution-only. `config/entry_panel.yaml` is compiled
during app composition with the active Action Language Pack's exact candidate
presentation into `EntryPanelCatalog`; the catalog implementation owns semantic
validity and lookup indexes while adapters own YAML shape, checksums and
error-path translation.

The canonical file owns categories, visual order, category copy and up to four
flagship candidates per scene. Each candidate is an explicit
`action_id + press_type` reference, so press-variant semantics are not guessed
by the UI. Candidate `label/description` come from the active pack as one
exact, restart-only resource. The canonical file does **not** duplicate prompts, input modes, provider choices,
keyboard mappings or availability logic. Validation fails application startup
when an action/variant is unknown, repeated across a location, a category is
invalid, or a flagship limit is exceeded. The digit assignments are structural
rather than duplicated configuration:

- Recent: 0–2.
- Top-level categories: 3–6 as defined by the PRD navigation scheme.
- Scene flagship actions: 1–4.
- More: no numeric mapping; use search, Tab, arrows, Enter or click.

Known unavailable actions remain visible and disabled with a reason. Actions
whose input/OCR viability is only knowable at execution are not pre-probed.

### 3. Two-stage typed admission into the established workflow

Expose a narrow typed `start_action(...) -> ActionStartAdmission` on
`WorkflowRuntimeModule`. It uses the current internal start path and accepts an
optional explicit `InputTarget`; the legacy `StartAction` command handler
continues to call the same behavior and may discard the result.

External input preparation is a separate, identity-scoped stage because target
activation and selection capture are blocking work. `EntryPanelRuntimeModule`
allocates one `EntryPanelSelectionId`, projects `preparing`, and schedules the
work through `TaskSupervisor`'s interactive lane. Completion returns through
the typed command queue with the same Panel lifecycle ID and selection ID. A
closed/reopened Panel, a second selection, cancellation or shutdown invalidates
the old identity; its late completion cannot start an Action or close the new
Panel. The existing clipboard transaction coordinator remains responsible for
safe restoration even when preparation becomes stale.

`ActionStartAdmission` is the single synchronous fact used to close the Panel:

- `accepted`: close Panel and let existing workflow/provider lifecycle run.
- `rejected`: keep Panel visible and show the reason.
- `blocked`: retain Panel with an explicit busy/voice message, as applicable.

Panel admission is explicitly identified at this seam. Its provider-busy policy
is checked again at final admission, while direct Shortcut policy remains
unchanged. A prepared workflow-result document retains its captured Workflow
and step lineage through admission; Workflow runtime validates that identity
instead of re-reading the current Foreground Workflow.

This avoids faking a shortcut, bypassing action execution, or treating a
provider notification as action acceptance.

### 4. Source selection and focus restoration

The source snapshot exists to preserve semantics, not to retain native
handles in the UI.

| Launch context | Source contract | On action selection |
|---|---|---|
| Unpinned Result Popup exists | Preserve that Popup as a temporary owned dialog and use its current selected/full semantic content. | Reuse the Popup workflow/source; do not read clipboard. |
| External application | Store opaque `ExternalWindowRef` at panel open. | Restore and validate target first, then request existing selection capture at action intent. |
| External target cannot be restored | No source fallback. | Keep Panel with a visible error; do not use latest clipboard. |

Use one generic external-window activation implementation for Panel capture and
keyboard Paste: modifier release, validation, focus evidence, revalidation and
the final cancellation check are shared. `PasteTarget` may use that
implementation, but the Panel must not use `PasteTarget` as its semantic source
or call native activation directly; Paste Dispatch truth remains in the
keyboard adapter.

For an external source, the intentional ordering is:

```text
select Action → Panel pending → restore/validate external target
              → InputResolver captures selection (clipboard fallback only inside its existing contract)
              → typed preparation completion with matching selection ID
              → explicit InputDocument/InputTarget → action admission
              → close Panel only if accepted
```

The explicit document prevents the workflow from capturing a second time after
the Panel or Popup has changed focus.

Closing or navigating while preparation is pending cancels the task when
possible and always invalidates the selection ID. A preparation failure restores
the same Panel projection with an actionable error; it must not fall back to a
new foreground window or a later clipboard value.

### 5. Independent UI surface with shared lifecycle

Add `UnifiedEntryPanelDialog` in its own UI module and use the existing single
hidden CustomTkinter root. Reuse `DialogLifecycle`, `NativeWindowSurface`,
display-metrics/pointer readers and current widget conventions. Do not reuse
`PopupControl`: it is coupled to workflow/paste/output identities and would
become a second owner if it absorbed the Panel.

Small reusable UI extraction: the presenter currently has a Popup-specific
focus-hold behavior for the shortcut guide. Extract an owned-control-surface
handoff capability rather than adding another private `_hold_*` special case.
Build the Panel content before deiconifying to prevent an empty shell flash.

UI behavior confirmed for the first release:

- Detailed density on every open; no density preference persistence.
- Search, Tab, arrow keys, Enter and click work in all applicable scenes.
- `Esc` immediately returns More to its scene; it does not first clear the
  filter. A subsequent `Esc` closes according to the panel flow.
- Click outside closes the full Panel.
- Top-row and numpad digits are both accepted after modifier-hold claim.
- Tooltips are keyboard-focus accessible, not mouse-only.
- The global platform Escape listener still routes a typed close request; Tk's
  local Escape handler returns `break` to avoid duplicate delivery.
- Provider response active: Panel may open but actions are disabled with a
  clear message; direct shortcuts retain their current behavior.
- Voice listening/finalizing: do not open Panel and do not interrupt voice;
  use existing voice feedback.

### 6. Recent actions are a small, independent aggregate

Introduce `RecentActionRef(action_id, press_type)` and `RecentActionHistory`.
It maintains a unique, most-recent-first top three list. It receives a precise,
typed `WorkflowStepAccepted(workflow_id, step_id)` event—not a workflow snapshot
revision. The event is enqueued only after `WorkflowController.complete`
accepts the active invocation. `WorkflowRuntimeModule` resolves that immutable
step and its root from the authoritative controller before sending the minimal
reference to `RecentActionHistory`; persistence contains only those two fields
with ordering in a dedicated atomic JSON file.

Confirmed policy:

- Replaying preserves the recorded press type.
- A follow-up moves the root action to the front.
- Headless speech completions count.
- Synthetic invocations do not count.
- Partial failures, cancellation, replacement and transport completion do not
  count.
- Persistence uses `TaskSupervisor` maintenance capacity with serialization or
  coalescing. A write failure updates the current in-memory view and records a
  safe diagnostic, but never changes the Action's real success to failure.

Do not put this aggregate in `UserPreferencesCoordinator` (explicit semantic
preferences) or `WorkflowController` history (per-workflow accepted steps).

## Contract sketch

| Contract | Layer | Key guarantee |
|---|---|---|
| `OpenUnifiedEntryPanel` | core command | Platform-to-runtime entry intent, carrying a launch/press identity; never an alias of `StartAction`. |
| `EntryPanelSource` | core immutable model | Popup semantic source or opaque external-window reference; no clipboard payload. |
| `EntryPanelCatalog` | services/config | Validated, display-only mapping to existing Action ID and press-type references. |
| `ActionStartAdmission` | core/app boundary | Exact accepted/rejected/blocked start result; only accepted permits Panel close. |
| `EntryPanelSelectionId` | core/app boundary | Prevents late target/input preparation from acting on a closed, reopened or newer Panel. |
| `EntryPanelInputPrepared` | core command | Returns an explicit document or typed preparation failure through the ordered command queue. |
| `InputTarget` | existing core model use | Carries the explicit `InputDocument`; the executor skips duplicate capture while Panel selection identity remains separate. |
| `WorkflowStepAccepted` | core/app command | Minimal accepted-step identity emitted only after controller acceptance; never carries user content. |
| `RecentActionRef` | core/services | Minimal replay reference; no user content or window metadata. |
| modifier-hold press identity | platform internal | Bounds timers, release, stale recovery and shutdown to one physical hold. |

## Consistency, error handling and privacy

| Scenario | Required behavior |
|---|---|
| Repeated Ctrl+Alt while Panel is open | Bring Panel forward; no new source snapshot, capture or action. |
| Modifier released early / non-modifier pressed early | Cancel only the hold candidate; never emit a short action. |
| External target restore/capture failure | Keep Panel, show error, no action and no stale-clipboard fallback. |
| Known unavailable action | Visible, disabled and explanatory; never hidden. |
| Provider timeout, partial failure, cancellation or replacement | Existing workflow behavior; no recent update. |
| Recent-store failure | Keep real Action result; record safe diagnostic; retry/coalesce through maintenance lane. |
| Configuration changes during execution | The admitted action retains its captured definition/input/provider binding; the next Panel sees new catalog configuration. |

Privacy boundaries:

- Persist recent action ID and press type only—never selected text, provider
  output, Popup text, external title, process metadata or clipboard contents.
- Use the existing container-scoped clipboard transaction coordinator; no
  parallel backup, restoration or logging flow.
- Diagnostics use failure category and safe identity/counter data only.

## Required verification

### Platform and runtime tests

- Ctrl+Alt at 1499 ms and 1500 ms; release-before-deadline; physical-state
  recheck; stale timer; injected event; shutdown; direct digit coexistence; no
  double invoke.
- Panel-open repeated hold; top-row/numpad claim while modifiers remain held.
- Voice listening/finalizing blocked; provider-response disabled state; direct
  shortcut behavior unchanged.
- All PRD action IDs compile in `entry_panel.yaml`; invalid/missing/duplicate
  catalog entries fail predictably.
- Popup source reuse; external target restore; capture at action intent;
  restore/capture failure; explicit input target prevents duplicate capture;
  closed/reopened/newer Panel rejects late preparation completion.
- `ActionStartAdmission` drives close/reject state; existing provider and
  workflow tests remain green.
- Recent ordering, dedupe, press-type replay, root-follow-up behavior,
  headless/synthetic policy, persistence failure and restart recovery.

### UI and desktop integration tests

- One Tk root/mainloop; no blank shell; focus handoff with existing Popup.
- Multi-monitor and DPI placement; work-area collision/quadrant flip; cursor
  preservation.
- Keyboard-only navigation, search, More/Esc behavior, disabled reason,
  top-row/numpad, click outside and tooltip focus access.
- Integration smoke covering external source → action selection → workflow
  admission → real lifecycle feedback, with zero provider work from the UI
  thread.

## Delivery plan and review gates

| Milestone | Deliverable | Exit gate |
|---|---|---|
| M1 | Modifier-hold contract, entry catalog validation, action admission and recent policy tests. | Boundary/timer/config/accepted-step unit tests pass. |
| M2 | Runtime source boundary, external-target activation port, explicit input target and atomic recent store. | No stale clipboard fallback; existing workflow/provider regression suite passes. |
| M3 | Independent Panel UI under a feature flag. | Focus, DPI, keyboard, accessibility and lifecycle integration smoke pass. |
| M4 | Controlled daily-use enablement and observation. | No P0/P1 focus, clipboard, double-invoke or hotkey regressions; persistence failures observable. |

Rollback is the feature flag or removal of the new entry command; existing direct
shortcuts and existing workflow behavior remain independently functional.

## Alternatives rejected

| Alternative | Why rejected |
|---|---|
| Add the Panel to `PopupControl` | It is already coupled to workflow/paste/output identities; the new surface would leak external-target and navigation policy into it. |
| Call `ActionExecutor` or provider directly from UI | Duplicates admission/cancellation/lifecycle and violates UI adapter boundaries. |
| Register `Ctrl+Alt` as an ordinary shortcut | Modifier-only semantics conflict with existing trigger-token, release and digit paths. |
| Derive recent actions from snapshots / put them in preferences | Neither is the precise success signal or appropriate owner for behavior history. |
| Build a WebView or second Tk root | Adds a second UI runtime and focus model without solving the source/action ownership problem. |

## Implementation-ready questions

No remaining product-direction decision blocks M1. The implementation review
must validate these repository-specific details before code starts:

1. The smallest extraction from existing native paste-target activation that
   provides `ExternalWindowRef` validation/activation without exposing raw
   handles to the Panel.
2. The smallest presenter lifecycle extraction that generalizes the current
   Popup focus-hold behavior without another private hold flag.
3. Initial `entry_panel.yaml` copy/category/flagship mapping and the exact PRD
   digit layout validation tests.
4. Real-device coverage for multi-DPI, multiple monitors, IME and numpad.

## Guardrails for the next implementation AI

- Preserve the owners table at the top of this document; do not solve a test
  failure by moving a side effect into UI or adding a second queue/registry.
- If a proposed change adds a raw dictionary across layers, global event,
  provider-specific UI branch, duplicate timer/focus/clipboard state, stop and
  record a new architecture diagnosis first.
- Treat identities as distinct: launch, selection capture, workflow,
  provider invocation, output operation and view lifecycle.
- Update contracts and targeted tests together; run focused tests, architecture
  tests, unit suite and a desktop integration smoke proportional to the change.
