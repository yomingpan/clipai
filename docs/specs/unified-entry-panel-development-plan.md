# Unified Entry Panel — Development Plan

Status: ready for implementation review

Branch: `codex/unified-entry-panel-development-plan`

Primary inputs: [product requirements](./unified-entry-panel-product-requirements.md)
and [system design](./unified-entry-panel-system-design.md)

This branch is a planning deliverable. It deliberately changes no production
code. Implementation starts only after the M1 contracts and test seams below
are accepted.

## 1. Executive judgment

**Classification: Yellow. Recommendation: incremental migration. Confidence:
high.**

The current action, input, provider and Workflow pipelines are reusable. The
risk is adding a second owner around two hot spots: physical hotkey timing and
Popup/focus lifecycle. The smallest safe intervention is an independent Entry
Panel slice that projects configuration and sends typed intents into the
existing `WorkflowRuntimeModule`.

This is not a Popup rewrite. It is also not a UI-only feature: external target
restoration and selection capture are asynchronous, identity-scoped operations
that must be coordinated outside the widget layer.

## 2. Triggering evidence

### Verified facts

- All 27 canonical action IDs in the PRD exist in `config/actions.yaml`.
- `WorkflowRuntimeModule._start_action` is the current start path for visible
  and headless Actions; `ActionExecutor` already resolves input, builds the
  request and uses `ProviderExecutionModule`.
- `InputTargetResolver` already makes a foreground Popup selection or canonical
  result outrank external selection/clipboard input.
- `InputResolver` performs external selection/clipboard capture through the
  container-scoped clipboard transaction owner.
- `WorkflowController.complete` is the acceptance point that appends an
  immutable successful `WorkflowStep`; provider completion alone is not enough.
- The hotkey listener already owns physical press identities, timers, release,
  stale-state recovery, injected-event handling and shutdown.
- `ResultDialogPresenter` currently contains Popup-specific owned-dialog focus
  hold fields for the Shortcut Guide. Recent history shows repeated focus and
  `PopupControl` changes, so adding another private hold flag would deepen the
  hot spot.
- `TaskSupervisor` already isolates interactive and maintenance blocking work.
- No Entry Panel feature flag or entry-catalog loader exists today.

### Inferences to validate during implementation

- The existing external-window observation data can be generalized into an
  opaque activation reference without giving the Panel paste semantics.
- One small owned-control-surface handoff seam can serve both Shortcut Guide and
  Entry Panel without exposing `PopupControl` internals.
- The mock's size is a useful baseline, but real multi-DPI measurements may
  require width adjustments to keep the header and three recent buttons usable.

## 3. Current capability and protected behavior

The existing execution pipeline must remain the only execution pipeline:

```text
typed Start Action intent
  → WorkflowRuntimeModule admission/membership/provider binding
  → ActionExecutor
  → InputResolver / PromptBuilder
  → ProviderExecutionModule
  → ResultProcessor / ResultRouter
  → WorkflowController accepted step
  → Popup projection
```

Protected behavior:

- Direct `Ctrl+Alt+digit` shortcuts keep their present short/long semantics.
- One Tk root/mainloop and at most one visible Workflow Popup remain invariant.
- Selection is captured at explicit Action intent, with valid selection before
  clipboard fallback and safe clipboard restoration.
- Pinned and unpinned Workflow replacement rules do not change.
- Provider, voice, output-operation and Paste identities remain separate.
- Pending, failure, cancellation and success UI reflect real lifecycle facts.
- No recent history contains source text, result text, titles, process metadata
  or clipboard data.

## 4. Four-part architecture diagnosis

### Ownership

| State or decision | Single owner |
|---|---|
| Physical `Alt` hold, deadline and claimed digits | platform hotkey listener |
| Entry catalog validation and key-to-candidate resolution | `EntryPanelCatalog` / `EntryPanelCoordinator` in services |
| Panel lifecycle, launch source and active selection-preparation identity | `EntryPanelRuntimeModule` in app |
| Panel widgets, focus evidence, placement and rendering | `UnifiedEntryPanelDialog` in UI |
| External window validation/activation | platform adapter behind a core port |
| Selection and clipboard transaction | existing `InputResolver` and `ClipboardTransactionCoordinator` |
| Workflow admission, membership and provider binding | existing `WorkflowRuntimeModule` |
| Successful Workflow step | existing `WorkflowController` |
| Top-three recent Action references | `RecentActionHistory` in services |
| Atomic recent-reference persistence | platform store adapter |

### Reusable capability versus exception

The reusable capabilities are modifier-hold input, configuration-backed entry
catalogs, external-window activation, typed Action admission and minimal recent
Action history. The PRD's three scenes, labels, flagship candidates, ordering
and copy are product configuration—not Python branches. The fixed product rules
are the maximum cognitive load, reserved key ranges and navigation semantics.

### Boundary propagation

Knowledge that must not cross its boundary:

- UI must not know provider readiness internals, clipboard APIs, native handles
  or Workflow replacement policy.
- Platform hotkeys must not know category IDs or Action IDs.
- `entry_panel.yaml` must not duplicate prompts, input modes, provider choices
  or execution availability rules from `ActionCatalog`.
- Recent persistence must not receive a `WorkflowStep` or snapshot containing
  user content; only `RecentActionRef(action_id, press_type)` crosses the store
  boundary.
- Workflow snapshot revision must not substitute for Panel lifecycle,
  selection preparation or successful-step identities.

### Enforcement

- Config parser tests reject unknown fields, unknown/repeated Action refs,
  invalid press types, duplicate/root key slots, more than four flagships and
  PRD-reserved key conflicts.
- Architecture tests keep `services` dependent only on `core`, keep native
  imports in `platform`, and forbid provider/clipboard imports in the Panel UI.
- Contract tests prove stale preparation and stale accepted-step events cannot
  mutate a newer Panel or recent history incorrectly.
- A single desktop smoke proves external source → selection capture → workflow
  admission without provider work on the UI thread.
- Boundary documents and their architecture tests are changed in the same
  commit as the module they constrain.

## 5. Debt multiplier

The multiplier is **special-case growth around shared lifecycle state**. The
hotkey listener and result presenter have already changed for distinct shortcut,
focus, voice, Paste and owned-dialog reasons. A Panel-specific timer in runtime,
an extra presenter hold flag or UI-driven input capture would create duplicated
ownership and make late completion invisible.

Three similar future changes without this intervention would likely require:

1. another Action picker to duplicate category/order/availability logic;
2. another owned dialog to add another Popup focus exception and cleanup path;
3. another launch gesture to race direct shortcuts with an unrelated timer.

The cost would be three new state machines that cannot be tested independently,
plus regression risk across focus, clipboard restoration and double invocation.

## 6. Realistic options

| Option | Benefit | Cost / risk | Reversibility |
|---|---|---|---|
| Accept a UI-only workaround | Fast mock-to-window path. | Duplicates focus, input and admission policy; cannot meet stale-operation rules. | Low once users rely on it. |
| Local refactor inside `ResultDialogPresenter` | Reuses current root quickly. | Makes the presenter own two unrelated surfaces and keeps category logic near widgets. | Medium. |
| **Incremental migration (selected)** | Adds only seams proven necessary and reuses all execution owners. | More contract work before visible UI; external focus needs desktop verification. | High: feature flag and typed command can be removed independently. |
| Core rebuild | Could rename every legacy Session/Popup surface at once. | Large unrelated migration with no product benefit for this feature. | Low. |

Only the incremental migration is recommended.

## 7. Recommended intervention

### Smallest boundary

Add one bounded feature slice:

- `services/entry_panel.py`: immutable catalog/projection and pure navigation,
  search, density, numeric resolution and disabled-state transitions;
- `services/recent_actions.py`: unique MRU policy over minimal Action refs;
- `app/runtime_entry_panel.py`: launch/source/selection-operation identity,
  blocking preparation scheduling, Workflow admission and projection routing;
- `ui/unified_entry_panel.py`: one CustomTkinter surface using the shared root;
- a platform recent store and the smallest external-target activator extraction;
- generic modifier-hold support inside the existing hotkey owner;
- typed core commands/models/ports required by those seams;
- `config/entry_panel.yaml` plus a disabled-by-default feature flag in
  `config/config.yaml` for staged rollout.

Do not create a second action executor, input resolver, clipboard coordinator,
provider task registry, event bus, Tk root, Popup control or preference
aggregate.

### Configuration contract

The entry catalog stores presentation and placement, not execution behavior.
Each candidate is an `action_id + press_type` reference so variant semantics are
explicit and recent replay remains accurate.

```yaml
schema_version: 1
categories:
  - id: understand
    slot: 3
    label: 看得懂
    description: 這段內容到底在說什麼？
    flagship:
      - action_id: translate_to_traditional_chinese
        press_type: short
        label: 翻譯成繁體中文
        description: 將內容轉成自然的繁體中文
    advanced: []
```

Rules:

- category count, IDs, root slots, names, descriptions, candidate order,
  flagship/advanced membership and copy come from configuration;
- recent slots `0–2`, category slots `3–6` and scene flagship slots `1–4`
  remain schema rules from the PRD;
- candidate copy may override the Action name for this surface, but prompt,
  input mode, output profile and provider policy remain in `ActionCatalog`;
- adding/removing/reordering a candidate requires config and validation tests,
  not UI code;
- known availability is joined from authoritative runtime capability owners;
  input or OCR viability that requires execution is never pre-probed.

### Open-time input preparation lifecycle

```text
OpenUnifiedEntryPanel
  → capture semantic Popup source or external-window reference
  → allocate preparation_id, project preparing and disable Actions
  → restore/validate captured external target
  → InputResolver captures selection and clipboard candidates once
  → EntryPanelInputPreparationCompleted/Failed(panel_id, preparation_id, ...)
  → reject if either identity is stale
SelectEntryPanelAction(panel_id, candidate)
  → resolve an Action-compatible InputTarget from frozen candidates only
  → WorkflowRuntimeModule.start_action(... explicit InputTarget)
  → accepted: close Panel; rejected/blocked: keep it with real reason
```

Popup-source opening skips external activation/capture and freezes selected
Popup text, otherwise the displayed canonical content. Closing, retry, reopen
and shutdown invalidate the old preparation ID. Cancellation never grants
an old worker authority over a new Panel.

### Successful-step to recent-history lifecycle

```text
WorkflowController accepts active invocation
  → enqueue WorkflowStepAccepted(workflow_id, step_id)
  → WorkflowRuntimeModule resolves immutable step/root from its controller
  → RecentActionHistory.record(RecentActionRef)
  → project in-memory result immediately
  → coalesced atomic save on TaskSupervisor maintenance lane
```

Synthetic steps are excluded by catalog membership/policy. Follow-up steps
resolve to their root Action. Headless direct Action success counts. Persistence
failure cannot alter the successful Workflow and must expose only safe
diagnostics.

### UI consistency

Before building the new surface, extract only the Popup visual tokens actually
shared by both surfaces (font family/sizes, surface/background, border/action/
content colors and neutral hover states) from `base_dialog.py` into a focused UI
theme module. Both the Popup and Panel consume those tokens; no values are copied
from the mock into a second theme.

The Panel builds content before `deiconify`, uses existing display metrics,
pointer/native-window ports and `DialogLifecycle`, and keeps tooltips keyboard
accessible. Local digit handlers ignore Ctrl/Alt-modified digits while the
global hold gesture owns them, preventing duplicate dispatch.

### Completion criteria

- All PRD flows and release-quality bullets have automated coverage where they
  do not require real desktop evidence.
- Direct shortcut, Workflow, provider, voice, clipboard and Popup suites remain
  green.
- Architecture tests prove the documented owners and dependency direction.
- Manual Windows smoke passes top-row/numpad, IME, multi-monitor/DPI, external
  focus restore, early release, click-outside and no-empty-shell scenarios.
- With the feature flag off, runtime behavior and registered direct shortcuts
  are unchanged.

## 8. Reversible migration and commit sequence

Each item is intended to be one cohesive commit. Do not combine M3 UI work with
M1/M2 contract changes.

### M1 — Contracts and pure policy

1. `docs: define unified entry panel contracts`

   Add `docs/adr/0012-unified-entry-panel-boundaries.md`,
   `docs/contracts/services/unified-entry-panel-contract.md`, update
   `docs/ARCHITECTURE_BOUNDARIES.md`, `docs/TESTING_STRATEGY.md`,
   `docs/contracts/platform/desktop-hotkey-listener-contract.md` and the native
   window contract. The documents must name all owners in section 4.
2. `feat: add typed entry panel contracts`

   Add immutable commands/models/ports and architecture tests only; no UI.
3. `feat: compile configurable entry panel catalog`

   Add `config/entry_panel.yaml`, loader/schema validation and table-driven
   service tests covering all PRD candidates and press types.
4. `test: specify entry panel navigation policy` then
   `feat: add entry panel coordinator`

   Red/green pure tests for root/scene/more navigation, search, density, disabled
   state, Esc and numeric resolution.
5. `test: specify recent action policy` then
   `feat: add recent action history`

   Red/green tests for top three, dedupe, follow-up root, headless/synthetic and
   persistence-independent in-memory behavior.

M1 gate: no toolkit or native calls in services; all configuration failures are
deterministic; architecture and pure unit suites pass.

### M2 — Input, runtime and persistence seams

6. `feat: add modifier-hold entry gesture`

   Extend the existing listener with identity-scoped exact-Alt 500 ms hold and
   digit claim. Preserve ordinary shortcut bindings. Add 499/500 ms, release, stale,
   injected, shutdown, repeated hold, top-row/numpad and no-double-invoke tests.
7. `refactor: generalize external target activation`

   Extract the minimum opaque reference/activation port from current Paste
   target mechanics. Keep native token parsing in platform. If a compatibility
   alias is required, mark removal for M4 and enforce that deadline in the ADR.
8. `refactor: expose typed workflow action admission`

   Make legacy `StartAction` and Entry Panel selection call the same
   `WorkflowRuntimeModule.start_action` path. Add explicit-input and
   accepted/rejected/blocked tests.
9. `feat: coordinate entry panel input preparation`

   Add `runtime_entry_panel.py`, identity-scoped interactive work and stale
   completion tests. No provider work starts before matching preparation.
10. `feat: persist recent successful actions`

    Add minimal accepted-step notification, root resolution, atomic platform
    store and coalesced maintenance writes. Test restart, corruption, write
    failure, privacy shape and headless ordering.

M2 gate: external selection is captured once at intent; late completion cannot
start work; existing provider/Workflow/input/Paste regression suites pass.

### M3 — Shared lifecycle and native UI

11. `refactor: introduce PrimarySurfaceHost for result Popup`

    Extract the native shell, mounted slot, bounds, DPI and drag lifecycle
    without changing Workflow or `PopupControl` semantics.
12. `feat: mount unified entry panel in primary surface`

    Implement config-driven Panel rendering as a replaceable view in the same
    host. Add widget, focus, keyboard, search, tooltip, Esc, click-outside,
    rollback, exact-bounds and no-empty-shell tests.
13. `feat: compose unified entry panel runtime`

    Wire config, runtime module, hotkey command, UI projection and recent store
    in `app/container.py`; keep the feature flag disabled by default.

M3 gate: one root/mainloop, no Popup ownership duplication, accessibility and
desktop integration smoke pass.

### M4 — Controlled enablement

14. `feat: enable unified entry panel for daily use`

    Enable only after real-device evidence is recorded. Remove any M2
    compatibility alias, update release/manual checklists and document rollback.

Rollback at every milestone is the feature flag plus removal of the new
modifier-hold command registration. Existing direct shortcuts and Workflow
execution remain independently functional.

## 9. Verification matrix

| Area | Targeted verification |
|---|---|
| Config/catalog | parser/schema tests; every PRD candidate resolves to an Action and press variant |
| Hotkey | platform hotkey and physical press lifecycle suites |
| Coordinator/history | pure service unit tests with table-driven transitions |
| Workflow admission | runtime tests for pinned/unpinned, provider readiness, voice and explicit input |
| Selection | input resolver and clipboard transaction suites plus stale preparation tests |
| UI | Panel unit tests, existing Popup/ResultDialog tests and shared-token regression |
| Architecture | import boundaries, native import ownership and new Panel boundary AST checks |
| Desktop | focused Windows integration smoke, then full unit suite and release checklist |

Minimum commands at the relevant gates:

```powershell
python -m pytest tests/architecture
python -m pytest tests/platform/test_hotkey.py tests/platform/test_hotkey_edge_cases.py tests/platform/test_shortcut_press_lifecycle.py
python -m pytest tests/services tests/app/test_runtime.py
python -m pytest tests/ui/test_popup_control.py tests/ui/test_result_dialog.py tests/ui/test_unified_entry_panel.py
python scripts/run_unit_tests.py
python -m pytest -m integration
```

## 10. Concise ADR

**Context:** ClipAI needs a lightweight, configuration-backed launcher without
changing direct shortcuts or duplicating Action execution. Modifier-only timing,
external focus and Popup ownership are already stateful boundaries.

**Decision:** Add a bounded Entry Panel with a services policy/coordinator, app
runtime owner, independent shared-root UI adapter, generic platform gesture and
activation ports, existing Workflow admission, and a minimal recent Action
aggregate.

**Alternatives:** Extending `PopupControl`, calling Action execution from UI,
registering modifier-only `Alt` as an ordinary shortcut and creating a second Tk/WebView
runtime are rejected because they duplicate an existing owner.

**Consequences:** More contracts and tests precede visible UI. In return, Action
candidates and flagship ordering change through config, external work is safely
identity-scoped, and the feature can be disabled without changing the existing
workflow path.

**Review trigger:** Revisit the boundary if a second non-Panel consumer needs
entry catalog navigation, if external activation failures remain common after
M4, if another module needs recent content rather than Action references, or if
the Panel needs persistent density/custom sorting.

## 11. Uncertainty and next inspection

No product-direction decision blocks M1. The highest-value implementation-time
inspection is a real Windows spike that measures focus restoration and selection
capture after the Panel yields foreground; unit doubles cannot prove compositor,
IME or target-application behavior.

The next highest-value checks are:

- whether the existing `PasteTarget` representation can be generalized without
  a compatibility alias;
- whether additional primary views can use `PrimarySurfaceHost` without
  contaminating `PopupControl`'s Workflow actuation ownership;
- initial multi-DPI width limits for the header and three recent buttons;
- the user-facing disabled reasons available from provider, Personal Style and
  voice owners without creating a second availability matrix.
