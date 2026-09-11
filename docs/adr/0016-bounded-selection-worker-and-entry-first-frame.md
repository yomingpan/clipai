# ADR-0016: Bounded selection worker and feedback-first Entry lifecycle

Status: accepted, 2026-09-11.

## 1. Executive judgment

Yellow, resolved by a local incremental migration with high confidence in the
automated policy and lifecycle behavior. The main reason is duplicated modifier
ownership plus per-request UIA process startup, not a need to rebuild the domain.

## 2. Triggering evidence

Observed: the existing worker was disposable, the clipboard transaction waited
for modifiers only after UIA, and `show_without_activation` always reactivated
the prior foreground. Prior device experiments attributed most latency to
interpreter/CLR startup and found 64 requests to be the useful reuse bound.
Inference: repeating these mechanisms would multiply latency and focus races.

## 3. Protected capability

Preserve exact HWND/PID source binding, fail-closed unknown/cancelled outcomes,
conditional clipboard restoration, feedback-first Entry Panel projection, one
primary surface, and direct-consumer correctness-first behavior.

## 4. Ownership, capability, propagation, enforcement

- Owner: `SelectionCaptureCoordinator` owns modifier gate/order and rebasing;
  `WindowsSelectionProbe` owns worker processes; app owns component lifetime.
- Capability: bounded source reuse and verified inner-source focus restoration
  are reusable platform capabilities, not Anki consumer branches.
- Propagation: only immutable booleans `copy_selection_only` and
  `focus_restored` cross platform into services.
- Enforcement: public-seam tests cover order, source mismatch, profile rejection,
  worker reuse/retirement/overflow, Entry-only fallback, first-frame hot paths,
  and shutdown convergence.

## 5. Debt multiplier

The multiplier was unmanaged process/concurrency state plus duplicated lifecycle
policy. Three similar exceptions would create three focus policies, repeated CLR
startup, and consumer-specific unsafe clipboard fallbacks.

## 6. Options

Keep disposable workers (simple, slow), build a worker pool (parallel but high
memory and focus ambiguity), broaden Copy/retry (small but unsafe), or keep one
bounded source owner plus isolated overflow. The last is bounded and reversible.

## 7. Decision

Reuse one healthy worker sequentially for the same HWND/PID, retire at 64 or on
source change/timeout/cancel/malformed/failure, and isolate overlap in one-request
processes. Gate modifiers before source/probe. Permit verified Anki inner-card
SetFocus without top-level activation and re-baseline in services. Preserve
feedback-first Entry display; make frozen clipboard fallback automatic only
there. Restore foreground after `SW_SHOWNOACTIVATE` only when it actually stole it.

## 8. Reversible sequence

Worker protocol and lifecycle were migrated first, then coordinator order and
typed focus evidence, then the narrow Anki profile, Entry/first-frame paths, and
finally app teardown. Removing a profile or reverting reuse does not change the
core consumer interface; no old and new owner paths remain active together.

## 9. Consequences and safeguards

The steady state retains one CLR worker instead of paying startup per request.
Overflow remains possible but never becomes a pool. `ExitStack` teardown and app
component registration prevent partial-shutdown leaks. Content-free JSONL gates
make regressions comparable without recording user content or executable paths.

## 10. Verification, uncertainty, and review trigger

The deterministic gate passed 480/480 for each of three seeds with 100% exact
availability for expected cases. A five-iteration interactive Windows benchmark
measured first-frame p95 101.270 ms and reclaim p95 9.279 ms against 150 ms.
The non-integration suite passed 1358 tests; 14 integration tests were deselected.
This run did not execute the opt-in real Anki selection smoke, so exact Anki/Qt
version behavior remains device evidence to collect. Review on any wrong-source
text, unknown direct fallback, worker leak, profile ancestry change, or first-frame
p95 regression above 150 ms.
