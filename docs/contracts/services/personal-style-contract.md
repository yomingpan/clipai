# Personal Style Contract

## Purpose

Personal Styles let a user import an explicit UTF-8 Markdown or text guide and apply one active profile to the three personal-voice Actions. The guide changes expression, never source meaning.

## Ownership

- `PersonalStyleCoordinator` is the single owner of imported profiles, the active profile identity, and import/select operation lifecycle.
- `JsonPersonalStyleStore` persists the aggregate atomically at `data/personal_styles.json`; it does not decide selection or workflow policy.
- `PersonalStyleRuntimeModule` supervises blocking file work and projects coordinator state. UI emits typed commands and never reads or writes style files directly.
- `WorkflowRuntimeModule` snapshots the active profile into the resolved Action before a Workflow or provider invocation starts. That snapshot remains stable for the Workflow step even if the active profile changes later.

## Admission and precedence

- An Action with `personal_style_mode` requires an active profile. Without one, the action visibly fails before provider execution.
- Actions without `personal_style_mode` are unchanged.
- The personal guide is subordinate reference data. Content fidelity, source language, attribution, Action output contract, and safety rules take precedence.
- Imported guide text is never silently summarized or truncated. Empty files, unsupported suffixes, invalid UTF-8, and files over 24,000 characters fail while preserving the previous active collection.

## Input and continuation

- External activation uses the existing selection-at-trigger policy with clipboard fallback.
- Inside a Popup, explicitly selected result text is used; otherwise the complete visible canonical result is used.
- No special parser extracts a bullet section or spoken section. Deduplication and format conversion are Action prompt policy.

## Action contracts

- `Ctrl+Alt+I`: one private, natural rewrite; repeated bullet/spoken content is expressed once.
- `Ctrl+Alt+O`: formal speakable prose; PREP-like order is used only when the source supplies its parts.
- `Ctrl+Alt+P`: unlabeled Markdown bullets, exactly one blank line, then formal spoken prose covering the same information.
