# ClipAI agent contract

Before changing this repository, read:

- `docs/Product_philosophy.md`
- `docs/ARCHITECTURE_BOUNDARIES.md`
- `docs/TESTING_STRATEGY.md`

## Product interaction principles

1. Every user action must produce an immediate, visible response. A control must show a pending, active, success, or failure state as appropriate; examples include Speak changing to Stop while active and Copy or Archive briefly confirming completion.
2. UI feedback must reflect the real lifecycle. Do not show success before the operation succeeds, and do not infer external API activity from unrelated UI or session revisions.
3. Accessibility and clarity take priority over decorative effects. Use a stable icon vocabulary, tooltips, enabled/disabled states, and state changes that remain understandable without animation.

## Architecture-first rule

1. Preserve architecture boundaries before adding feature-specific behavior. Put policy in core/services, orchestration in app, and toolkit or OS behavior in adapters.
2. If a requested feature needs a one-off dependency, bypass, global event, raw cross-layer dictionary, or provider-specific UI branch, stop and warn that it will constrain future architecture changes. Describe the coupling and propose a reusable contract or adapter boundary before implementation.
3. Do not add an abstraction speculatively. Add one when it removes actual coupling, duplication, or state ambiguity in the current design.
4. UI must not directly call clipboard, keyboard, TTS, archive, or provider implementations. Use typed commands and injected ports.

## Dependency boundaries

- `core` depends only on the Python standard library.
- `services` depends on `core`.
- `platform`, `providers`, and `ui` depend on `core` plus their adapter libraries.
- Only `app` composes concrete services, platform adapters, providers, and UI.
- Cross-thread UI input uses the typed command queue, not a global Event Bus.
- A session has one `SessionController` as its state owner.
- Provider workers never mutate Tkinter; UI changes happen on the UI thread.
- Use typed immutable models between layers instead of raw dictionaries.

## Change workflow

1. Check `git status --short` and preserve unrelated user changes.
2. Keep each change cohesive and update its contracts and tests together.
3. Run targeted tests, architecture tests, the unit suite, and an integration smoke test in proportion to the change risk.
4. Search imports, tests, config, scripts, and docs before removing or renaming a public surface.
5. Before committing, inspect `git diff --cached` and use a scoped commit prefix such as `feat:`, `fix:`, `refactor:`, `test:`, or `docs:`.
