# Inline Dictation ownership diagnosis (2026-09-29)

## Judgment

Yellow before implementation; a bounded local refactor was warranted. Confidence:
high. `ResultDialogPresenter` held both the Inline window identity and five modal
dialog lifecycles, so further UI changes would have added unrelated state there.

## Evidence and protected behavior

Before this change, `ui/result_dialog.py` stored `_inline_dictation_window` and
the five modal fields. Its Inline methods checked interaction IDs and scheduled
terminal dismissal; its modal methods constructed and closed dialogs. Tests in
`tests/ui/test_result_dialog.py` covered stale Inline completion and shortcut
guide focus restoration. The verified behavior to preserve was identity-scoped
late-result rejection, modal focus restoration, and unchanged command timing.

## Diagnosis

- **Owners:** `InlineDictationInterfaceOwner` now owns the Inline window and
  interaction ID. `OwnedModalRegistry` owns the five dialogs. The result
  presenter retains Popup focus coordination. `VoiceCaptureAdmissionPolicy`
  owns admission decisions; `WorkflowRuntimeModule` supplies facts.
- **Capability:** These are reusable UI lifecycle and admission boundaries,
  rather than exceptions for a single button or provider.
- **Propagation:** Window existence and modal construction previously crossed
  through the result presenter. Runtime now receives the dedicated Inline
  presenter through composition; the UI owner emits only typed commands.
- **Enforcement:** `tests/architecture/test_inline_ui_ownership.py` rejects
  reintroduced window fields and iteration in the cross-thread Popup query.
  UI owner, policy, runtime, and journey tests preserve the behavior matrix.

The debt multiplier was duplicated responsibility in a broad presenter. Three
similar future changes would each need to touch Popup rendering, Inline view
identity, and modal construction, raising the chance of stale callbacks and
cross-feature regressions.

## Options and decision

Keeping the presenter as-is had no migration cost but left the multiplier.
A full UI rewrite had a much larger behavior and timing risk. The chosen local
refactor moved each lifecycle to one owner and kept the existing public Popup
methods as delegation points. The move is reversible by restoring the prior
method bodies, though doing so would restore the coupling.

The migration used rejection tests, extracted the admission policy and UI
owners, rewired composition, and ran focused and full gates. Completion is
observable in the 1826-case non-integration regression, 56-case architecture
slice, and the identity-scoped owner tests. Toolkit, provider, and clipboard
behavior were outside the ownership refactor.

## ADR and review trigger

**Context:** One presenter held unrelated view lifecycles. **Decision:** Keep
one owner per lifecycle and let the presenter coordinate focus only.
**Alternative:** Retain the broad presenter or rewrite all UI composition.
**Consequence:** New Inline or modal behavior has a named testable owner.
Review this boundary if a new dialog requires a second registry or if a new
Inline state must again be stored in `ResultDialogPresenter`.

The highest-value remaining inspection is an attended multi-monitor Windows
run that changes DPI while the Inline window is open. The deterministic tests
verify the callback and geometry rules but do not provide device evidence.
