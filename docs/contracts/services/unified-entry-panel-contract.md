# Unified Entry Panel Contract

## Purpose

The Unified Entry Panel is a short-lived Action launcher. It is not a Workflow,
chat, result Popup, shortcut catalog or execution pipeline. It presents recent
successful Action references and a configuration-backed information hierarchy,
then requests admission through the existing Workflow runtime.

## State ownership

- `EntryPanelCoordinator` owns the immutable projection: page stack, detailed
  versus compact density, search text, focused candidate, disabled candidates,
  per-option pending projection and transient message. It receives the
  saved density from `UserPreferencesCoordinator` at composition time; the
  existing user-preferences lifecycle persists later density changes.
- `EntryPanelRuntimeModule` owns the one live Panel lifecycle ID, captured source
  reference, open-time preparation scheduling/cancellation, frozen
  `PreparedEntryInput` and the transition to Workflow admission.
- `UnifiedEntryPanelDialog` owns only toolkit widgets, focus evidence, placement,
  hide-before-destroy teardown and mechanical rendering. Header dragging reuses
  the UI-layer window drag controller; every semantic user operation emits a
  typed command.
- `EntryPanelCatalog` owns validated presentation metadata：category slot/ID、
  flagship limit、candidate uniqueness 與 existing `action_id + press_type`
  membership，並提供其 lookup indexes。Canonical config adapter 提供 IA shape；
  active Action Language Pack 提供 exact candidate `label/description`；app
  composition 只在兩者完整吻合後建立 catalog。
- `RecentActionHistory` owns the unique most-recent-first top three references.

## Legal lifecycle

```text
closed → open(root) → navigating/searching/density toggle
       → preparing(preparation_id) → ready(frozen input)
                    → failed → explicit retry(same source, new preparation_id)
                    → rejected/blocked → ready(previous page)
                    → admitted → closed
```

Opening is the explicit intent that authorizes input preparation; rendering,
focus, navigation and density changes never imply Action execution. While
preparing, otherwise-capable Actions remain enabled in the capability projection
but carry `pending=True`; both the pure coordinator and UI intent adapter reject
their invocation. A real policy or input incompatibility takes precedence,
projects `enabled=False` with its authoritative reason, and is the only red
disabled state. A close invalidates the preparation identity.
Only a completion matching both Panel lifecycle ID and preparation ID may publish
the frozen input. Action selection resolves only that immutable bundle and never
reads selection, clipboard or foreground state.

`Esc` always emits `CloseEntryPanel`, immediately closes any page and cancels
matching preparation. `EntryPanelBack` is a distinct typed intent: the left
header control and `Ctrl+Z` navigate More → scene → root; Back at root is a
no-op and never closes. Navigation preserves Panel lifecycle, source preview,
density, pending/error projection and frozen input.

The Panel closes only after `ActionStartAdmission.accepted`. A rejected or
blocked admission keeps the same Panel and projects the authoritative reason.
An accepted admission identifies its Workflow. Runtime registers a visual
replacement with both Panel and Workflow identities before the first Workflow
projection; a stale or unrelated projection cannot consume it.

`PrimarySurfaceHost` retains one native shell while the result view is built
off-slot and then identity-matched into the mounted content slot. Mount failure
keeps the same Panel mounted; the Panel view is closed only after `replace()`
succeeds. If admission reuses an existing Popup, its
unmounted view is updated and remounted without changing shell geometry.
`PopupBounds` stores physical screen position with toolkit-logical width/height;
physical widget dimensions must not be fed back as logical geometry. This is
presentation actuation only and does not merge Panel navigation with
`PopupControl` or Workflow state.

## Input source

- A foreground Workflow Popup freezes its explicit semantic selection or
  canonical displayed content before the Panel takes focus; no clipboard read
  occurs.
- Otherwise the Panel captures one opaque external-window reference at open.
  After the Panel is projected, preparation restores and validates that exact
  target, waits for modifiers to release, captures every supported input fact
  through the existing `InputResolver`, then confirms the same target still owns
  foreground. Confirmation may wait within a bounded, cancellation-aware window
  for the exact target to recover from an IME transient. Expiry fails closed and
  does not automatically repeat selection capture.
- Failure does not substitute the current foreground window or a later clipboard
  value.
- `PreparedEntryInput` resolves the already frozen `InputDocument` for the
  selected Action's `InputMode`; it enters Workflow admission through
  `InputTarget`, so neither runtime selection nor `ActionExecutor` captures a
  second time.
- A workflow-result document keeps its captured `workflow_id + step_id` through
  final admission. Workflow runtime validates that lineage against its own
  membership/history; it never substitutes the current Foreground Workflow.
- Cancellation and stale completion do not weaken the existing clipboard
  transaction restoration rules.

## Catalog and numeric rules

- Candidate order、category copy 與 flagship/advanced membership 來自
  `config/entry_panel.yaml`。Candidate Action `label/description` 來自 process
  啟動時選定且完整驗證的 Action Language Pack。
- Recent slots are `0`–`2`, root category slots are `3`–`6`, and scene flagship
  slots are `1`–`4`. More/search has no digit mapping.
- Each candidate explicitly names Action ID and press type. The catalog rejects
  unknown Actions/variants, duplicates, invalid slots and more than four
  flagships.
- Action prompts, input/output modes, provider policy and Personal Style policy
  remain in `ActionCatalog` and authoritative capability owners.
- Configuration change affects the next Panel; an admitted invocation retains
  its already captured Action definition, input and provider binding.
- Action Language selection is restart-only. Persisting a next-start pack does
  not mutate the current Panel catalog; after restart, Recent references are
  re-projected through the new active pack without persisting localized text.

## Recent success

- Only a `WorkflowStep` accepted by `WorkflowController.complete` is eligible.
- Runtime resolves follow-up steps to the root catalog Action. Synthetic roots,
  failures, cancellation, replacement and transport-only completion do not
  count. Headless direct Action success does count.
- In-memory history updates immediately. Atomic persistence runs in maintenance
  capacity and stores only `action_id`, `press_type` and ordering.
- Persistence failure does not change Workflow success and must not log user
  content, window metadata or clipboard data.

## Verification boundary

Public tests exercise `EntryPanelCatalog`, `EntryPanelCoordinator`,
`RecentActionHistory`, the typed runtime command seam, the hotkey listener and
the UI projection/intent port. Open-time preparation tests prove source capture,
frozen mode resolution, preview, retry and late-completion rejection. Identity,
mount, replace, commit order, rollback, bounds and reused-Popup behavior are
tested through the `PrimarySurfaceHost` interface; presenter tests retain only
the integration needed to prove delegation from Workflow rendering. Runtime
tests additionally prove replacement registration precedes the first visible Workflow projection and
that post-capture target loss cannot admit clipboard fallback. Tests do not
inspect private presenter transition state, private runtime methods or internal
state dictionaries.

UI lifecycle tests additionally lock `_body_render_key` to topology and visible
static detail only. Per-option `enabled/pending/disabled_reason` changes update
existing cards in place. Both updater and click callback read the latest option;
opening and preparation settlement must not rebuild the body.
