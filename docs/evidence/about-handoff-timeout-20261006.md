# About host preparation timeout — 2026-10-06

## 1. Executive judgment

Yellow; recommend a local refactor of the platform handoff polling deadline.
Confidence is high for the reproduced client failure. Its 20-second default
expires before the reported 78-second preparation completes. Production repair
follows this diagnosis and stays within the existing handoff owner.

## 2. Triggering evidence

The user reports another computer's sequence: request, client timeout at 20s,
candidate 3.7.13 ready at 78s, then host shutdown_failed because the old App
remains running. Raw event artifacts from that machine are not available here.

The actual App executor plus platform handoff, with a virtual clock and ready
artifact at 78s, fails at 20s. Before repair:

```text
.venv/Scripts/python.exe scripts/run_unit_tests.py -- tests/app/test_managed_update_client_handoff.py -k 78_second -q
1 failed, 2 deselected (handoff_timeout), 0.34s
.venv/Scripts/python.exe scripts/run_unit_tests.py -- tests/platform/test_managed_update_handoff.py tests/app/test_managed_update_client_handoff.py -q
5 failed, 6 passed, 0.61s
```

The additional red cases cover readiness at 480s, readiness exactly at a
configured deadline, and finite default waiting. These are simulated timing
tests against real file artifacts, not a replay of the user's machine.
Baseline HEAD: b3422eb04bcdbb58300642498322e5aa458d205c, with prior fixes retained.

## 3. Current capability and protected behavior

The stable host verifies and materializes a candidate before publishing ready.
The installed App then requests normal runtime shutdown. Transaction ordering,
signature checks, exact readiness identity, retained process identity, and
keeping the old App running on failure must remain intact.

## 4. Four-part diagnosis

- Ownership: SubprocessManagedUpdateHandoff owns the client preparation wait;
  ManagedUpdateHost owns transaction execution and its separate shutdown and
  health waits. AppRuntime owns normal App shutdown.
- Capability: waiting for an offline prepared payload is reusable behavior,
  not an exception for one computer or one release.
- Propagation: the client deadline ignores the builder's four independently
  bounded 120-second commands. Preparation was effectively given the much
  smaller shutdown-style budget. No new cross-layer dictionary is needed.
- Enforcement: contract plus tests at the actual App-to-platform seam cover
  slow preparation, deadline-boundary proof validation, terminal failure,
  finite timeout, and transaction-scoped late readiness.

## 5. Debt multiplier

Unrelated lifecycle phases share an assumed small time allowance and lack a
slow-machine regression. Three more timing fixes implemented as release-specific
exceptions would multiply deadline configuration and contradictory behavior.
One preparation default and phase-specific contracts avoid that growth.

## 6. Options

Accepting 20s is cheap but preserves the reproduced failure. A local deadline
repair is small, testable, and reversible, at the cost of allowing a failed
preparation to remain pending longer. An incremental abort/cleanup protocol has
broader cross-process ownership costs and is unnecessary for this timing defect.
A core rebuild has no evidence-backed benefit here.

## 7. Recommended intervention

Use a 600-second default preparation allowance: four 120-second offline commands
plus 120 seconds for verification, filesystem work, and scheduling. This is a
bounded client wait, not a claim that all filesystem calls have hard OS timeouts.
Sample terminal result and exact ready evidence once at the deadline before
reporting timeout; cap each polling sleep to the remaining allowance.
Do not change the host's independent 20-second shutdown or health budgets.
Do not add another cancellation, shutdown, or cleanup owner. A late ready file
after a completed timeout must not independently shut down the App or satisfy a
different transaction. Completion requires the regression loop, architecture,
unit suite, and managed-bundle smoke gate to pass.

## 8. Reversible sequence

Record diagnosis; write and run failing regressions; change the single adapter
deadline and polling loop; update its contract; run targeted and broader gates.
Existing published release assets remain immutable. Delivery of the client fix
requires a newly built client candidate; changing only the target bundle cannot
extend the already installed client's wait.

## 9. ADR

Context: candidate materialization exceeds the client default on another PC.
Decision: keep preparation waiting in the existing adapter and give it a finite
600-second default, with a final proof sample. Alternatives: 20s, unbounded wait,
or a new abort protocol. Consequence: slower preparation can complete; genuine
timeouts still preserve the running App. Review trigger: preparation repeatedly
exceeds 600s, or abandoned host transactions obstruct retry; then diagnose the
cross-process abort and candidate cleanup contract separately.

## 10. Uncertainty

The user's 78s timing is reported evidence. Full elapsed time, reboot, retained
settings, and real About success on the other PC still require a fixed client
candidate. A true timeout can leave an inactive prepared candidate before the
host reports shutdown_failed; this repair does not claim to clean that case.

## Validation

The platform default is now 600 seconds; polling performs the final evidence
sample and never sleeps beyond the remaining allowance. No debug instrumentation
or additional state owner was introduced.

- Targeted platform/App loop: 14 passed in 2.41s, after 7 failed / 7 passed
  before repair. The 78-second virtual-clock scenario reaches normal App shutdown
  at 78s instead of raising handoff_timeout at 20s.
- Architecture: 56 passed in 6.54s.
- Full unit suite: 1,974 passed, 64 integration cases deselected, 61.14s.
- Managed-update synthetic transaction: 1 passed in 0.16s.
- Loopback HTTPS integration: 2 passed in 2.10s.
- Signed managed-bundle integration: 2 passed in 116.57s; offline environment
  construction, identity-bound launch health, transaction fault/rollback matrix,
  preserved shared user data, and successful finalization. Full gate exit code 0.
- `git diff --check`: passed; normal index remains unstaged.

Full managed gate command and log:

```text
.venv/Scripts/python.exe scripts/verify_managed_update.py --stage managed-bundle
artifacts/about-handoff-timeout-20261006/managed-bundle-gate.log
```

Repair is in the working source, not in the existing public 3.7.12/3.7.13 assets.
Real About success, retained settings, reboot, and fixed-client release delivery
are not inferred from these simulated or packaging checks.
