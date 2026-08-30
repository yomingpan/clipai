# Unified Entry Panel Contract

## Purpose

The Unified Entry Panel is a short-lived Action launcher. It is not a Workflow,
chat, result Popup, shortcut catalog or execution pipeline. It presents recent
successful Action references and a configuration-backed information hierarchy,
then requests admission through the existing Workflow runtime.

## State ownership

- `EntryPanelCoordinator` owns the immutable projection: page stack, detailed
  versus compact density, search text, focused candidate, disabled candidates,
  transient message and active selection-preparation identity. It receives the
  saved density from `UserPreferencesCoordinator` at composition time; the
  existing user-preferences lifecycle persists later density changes.
- `EntryPanelRuntimeModule` owns the one live Panel lifecycle ID, captured source
  reference, selection-preparation scheduling/cancellation and the transition to
  Workflow admission.
- `UnifiedEntryPanelDialog` owns only toolkit widgets, focus evidence, placement
  and mechanical rendering. Every user operation emits a typed command.
- `EntryPanelCatalog` owns validated presentation metadata and maps candidates
  to existing `action_id + press_type` references.
- `RecentActionHistory` owns the unique most-recent-first top three references.

## Legal lifecycle

```text
closed → open(root) → navigating/searching/density toggle
                    → preparing(selection_id)
                    → rejected/blocked → open(previous page)
                    → admitted → closed
```

Opening, rendering, focus, navigation and density changes never imply Action
execution. While preparing, another selection replaces the old identity and a
close invalidates it. Only a completion matching both Panel lifecycle ID and
selection ID may call Workflow admission.

The Panel closes only after `ActionStartAdmission.accepted`. A rejected or
blocked admission keeps the same Panel and projects the authoritative reason.

## Input source

- A foreground Workflow Popup supplies its explicit semantic selection or
  canonical displayed content; no clipboard read occurs.
- Otherwise the Panel captures one opaque external-window reference at open.
  On selection it restores and validates that exact target before calling the
  existing `InputResolver` at explicit user intent.
- Failure does not substitute the current foreground window or a later clipboard
  value.
- Prepared `InputDocument` enters Workflow admission through `InputTarget`, so
  `ActionExecutor` does not capture a second time.
- Cancellation and stale completion do not weaken the existing clipboard
  transaction restoration rules.

## Catalog and numeric rules

- Candidate order, category copy, descriptions and flagship/advanced membership
  come from `config/entry_panel.yaml`.
- Recent slots are `0`–`2`, root category slots are `3`–`6`, and scene flagship
  slots are `1`–`4`. More/search has no digit mapping.
- Each candidate explicitly names Action ID and press type. The catalog rejects
  unknown Actions/variants, duplicates, invalid slots and more than four
  flagships.
- Action prompts, input/output modes, provider policy and Personal Style policy
  remain in `ActionCatalog` and authoritative capability owners.
- Configuration change affects the next Panel; an admitted invocation retains
  its already captured Action definition, input and provider binding.

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
the UI projection/intent port. They do not test private widget helpers, private
runtime methods or internal state dictionaries.
