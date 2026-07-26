# ClipAI agent contract

Before changing this repository, read:

- `docs/Product_philosophy.md`
- `docs/ARCHITECTURE_BOUNDARIES.md`
- `docs/TESTING_STRATEGY.md`

## Product interaction principles

1. Every user action must produce an immediate, visible response. A control must show a pending, active, success, or failure state as appropriate; examples include Speak changing to Stop while active and Copy or Archive briefly confirming completion.
2. UI feedback must reflect the real lifecycle. Do not show success before the operation succeeds, and do not infer external API activity from unrelated UI or workflow snapshot revisions.
3. Accessibility and clarity take priority over decorative effects. Use a stable icon vocabulary, tooltips, enabled/disabled states, and state changes that remain understandable without animation.

## Architecture-first rule

1. Preserve architecture boundaries before adding feature-specific behavior. Put domain contracts in `core`, testable use-case policy and workflow coordination in `services`, runtime dispatch and composition in `app`, and toolkit or OS behavior in adapters.
2. If a requested feature needs a one-off dependency, bypass, global event, raw cross-layer dictionary, or provider-specific UI branch, stop and warn that it will constrain future architecture changes. Describe the coupling and propose a reusable contract or adapter boundary before implementation.
3. Do not add an abstraction speculatively. Add one when it removes actual coupling, duplication, or state ambiguity in the current design.
4. UI must not directly call clipboard, keyboard, TTS, archive, or provider implementations. Use typed commands and injected ports.

## Progressive architecture diagnosis

Temporary architectural ambiguity is acceptable during exploration only when it
is visible, reversible, locally contained, and has a defined review trigger.

Invoke `progressive-architecture-diagnosis` before adding another workaround
when ownership is unclear; a similar bug occurs twice; a second state, queue,
workflow, validation, or configuration mechanism appears; one module changes
across three distinct feature requests; or architecture begins to affect
delivery speed or product choices.

A trigger requires diagnosis, not automatic refactoring. The diagnosis must
identify a single owner (or explicitly state its absence), distinguish reusable
capability from special case, trace boundary leakage, and propose at least one
enforceable safeguard. Do not modify production code as part of the diagnosis
unless the user explicitly asks for implementation.

## Intent and lifecycle rules

1. Side effects require an explicit typed user intent. Speech, paste, archive, clipboard mutation, provider calls, and diagnostics export must not be inferred from view creation, render, focus, activation, navigation, provider completion, or workflow snapshot revision.
2. Workflow identity, provider invocation identity, output-operation identity, selection-capture identity, and view lifecycle are separate concepts. Do not substitute one identity or a workflow snapshot revision for another. Existing `session_id` fields and `SessionSnapshot` are compatibility names for Workflow identity and projection; do not introduce a second Session domain concept or add new session-named surfaces.
3. Cancellation, cleanup, clipboard restoration, and late completion are scoped to the operation identity that created them. An older operation must never cancel, overwrite, restore into, or report completion for a newer operation.
4. Every Workflow has exactly one authoritative state owner: `WorkflowController` owns its snapshot, active invocation, cancellation, successful-step history, and feedback projection. `WorkflowRuntimeModule` separately owns Workflow membership, semantic Foreground Workflow identity, visible/headless lifetime, and the provider binding captured at Workflow start. Widgets, workers, and adapters may project or report state but must not duplicate either ownership role.
5. Operation-specific state such as speaking, copying, archiving, or provider activity must reflect the real operation lifecycle. Do not derive it from view visibility or workflow snapshot revisions.
6. For every text-capable Action, prefer text explicitly selected at the instant the user triggers the Action; when no valid selection can be captured, fall back to the clipboard. Selection capture must not permanently change the user's previous clipboard content.

## Dependency boundaries

- `core` depends only on the Python standard library.
- `services` depends on `core`.
- `platform`, `providers`, and `ui` depend on `core` plus their adapter libraries.
- Only `app` composes concrete services, platform adapters, providers, and UI. `app/container.py` is the assembly entry point; focused app composition adapters may construct or rebuild concrete dependencies behind typed service contracts.
- Cross-thread UI input uses the typed command queue, not a global Event Bus.
- Provider workers never mutate Tkinter; UI changes happen on the UI thread.
- Use typed immutable models between layers instead of raw dictionaries.
- Reusable orchestration that can be tested without the concrete desktop runtime belongs in `services`; `app` owns composition, command dispatch, runtime lifecycle, and coordination across use cases.

## Presentation and UI adapter boundaries

1. Canonical result content is independent of widget styling. Copy, paste, archive, and speech must consume an explicit semantic content source, not reconstruct content from styled widgets.
2. Parsing and presentation transformation produce a typed immutable presentation model at a testable presentation boundary. UI adapters render that model and must not implement scattered Markdown or format parsing.
3. Unsupported presentation syntax must degrade to safe plain text without losing canonical content or crashing the popup.
4. UI adapters may interpret toolkit lifecycle events such as focus, activation, deiconify, geometry, DPI, and click-outside detection. They emit typed semantic commands such as close requests; they do not directly change workflow policy or introduce a global mouse event bus.
5. Capability availability, enabled state, operation lifecycle state, and visual placement are separate concerns. Core/services own capability and operation state; the presentation layer decides primary versus overflow placement; UI adapters render the result.

## Change workflow

1. Check `git status --short` and preserve unrelated user changes.
2. Keep each change cohesive and update its contracts and tests together.
3. Run targeted tests, architecture tests, the unit suite, and an integration smoke test in proportion to the change risk.
4. Search imports, tests, config, scripts, and docs before removing or renaming a public surface.
5. Before committing, inspect `git diff --cached` and use a scoped commit prefix such as `feat:`, `fix:`, `refactor:`, `test:`, or `docs:`.
