# ADR 0001: Personal Recipe prompt overlay

## Status

Accepted for the local, non-synchronizing Recipe improvement feature.

## Context

Built-in Action definitions and prompts remain owned by `config/actions.yaml` and
loaded through the existing config-loader boundary. Users cannot edit that file,
but need to apply and restore personal prompt-only revisions at runtime.

Creating a second Action catalog or rewriting `config/actions.yaml` would split
Action ownership or make product updates overwrite personal changes.

## Decision

`ActionCatalog` remains the single authoritative resolver for executable Actions.
It keeps the immutable built-in definitions loaded from `config/actions.yaml` and
may project one active, prompt-only overlay per `(action_id, press_type)`.

`app/recipe_configuration.py` is the focused composition boundary that loads the
local overlay and publishes it into that catalog. The JSON adapter stores
immutable personal revisions and active pointers; it is not itself an Action or
prompt owner. `RecipeRevisionCoordinator` validates stale parents and performs
persist-before-publish transactions.

The overlay may change only `system_prompt` and `prompt`. Every other executable
Action field continues to come from the built-in definition. Corrupt overlay
storage preserves the file, leaves built-in Actions active, and disables writes.

## Consequences

- Built-in updates cannot overwrite personal prompt revisions.
- New invocations resolve the active overlay without restarting ClipAI.
- Existing Workflow lineages retain the `ResolvedAction` revision they captured.
- Any future prompt source must compose through this same boundary and catalog;
  it must not introduce another runtime Action registry.
