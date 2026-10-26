# About startup health timeout — 2026-10-06

## 1. Executive judgment

Yellow; recommend a bounded local repair of the shared startup-health budget
and the existing lifecycle poller. Confidence is high for both reproduced
defects. Do not create a second transaction, readiness, or process owner.
This diagnosis precedes production edits; the reported bug authorizes repair.

## 2. Triggering evidence

The user reports that 3.7.14 successfully hands off to prepared 3.7.15, but
the candidate's roughly 20-second startup exceeds the health wait. The host
rolls back and relaunches 3.7.14, which reports healthy. This confirms the
previous handoff repair on that machine; full update acceptance failed.
Raw logs from that machine are unavailable here.

The real Host executor, filesystem transaction and subprocess lifecycle with
an injected clock reproduce a 30-second healthy startup becoming
`rolled_back`, `health_timeout`, active 1.0. Explicitly supplying 120 seconds
makes that scenario pass without changing its identity or health reporter.
Even with explicit 120 seconds, a receipt exactly at the deadline is missed.
The platform loop also oversleeps a 1.0-second budget to 1.2 seconds.

```text
.venv/Scripts/python.exe scripts/run_unit_tests.py -- tests/app/test_managed_update_host.py tests/platform/test_managed_update_lifecycle.py -k 'slow_startup or health_deadline' -q --tb=short
10 failed, 2 passed, 13 deselected in 6.43s
artifacts/about-health-timeout-20261006/red-regression.log
```

Ranked hypotheses: insufficient default (confirmed by explicit-budget probe);
deadline final-sample omission (confirmed independently); mismatched readiness
identity (not the cause of the synthetic slow case). These timing tests are
deterministic simulations with real typed artifacts, not a machine-log replay.
Initial direct pytest invocations failed in temporary-directory setup; the
repository test runner supplies writable isolated storage and runs the repro.

## 3. Current capability and protected behavior

Managed updates verify and prepare before shutdown, commit an atomic pointer,
launch the exact candidate, require genuine runtime readiness, and finalize.
Failure restores the pointer, proves the owned candidate stopped, then launches
and health-checks the old version. Preserve signatures, shared user data,
attempt identity and the runtime's real readiness boundary.

## 4. Four-part diagnosis

- Ownership: services owns health-budget policy and transaction/rollback
  decisions; the platform lifecycle owns waiting for typed health artifacts
  and processes it starts. App composes these owners. Runtime reports readiness.
- Capability: bounded slow-startup tolerance applies to updates, rollback,
  interrupted recovery and ordinary managed startup, rather than one machine.
- Propagation: four constructors independently default to 20 seconds. A host
  edit alone leaves normal launch and direct service composition inconsistent.
  No UI or release-specific override should own startup policy.
- Enforcement: one services constant supplies all four defaults. Regression
  tests exercise slow startup through the real host, exact-deadline validation,
  finite absence/stale waits, late candidate evidence during rollback, and
  exact process stop-before-relaunch ordering; contracts specify the policy.

## 5. Debt multiplier

Duplicated phase defaults plus missing slow-startup and final-sample cases
allow drift. Three similar fixes would require auditing four constructors each
time and could produce different behavior for launch, update and recovery.
One startup default removes this concrete duplication. Preparation and process
shutdown remain separately bounded phases with different purposes.

## 6. Options

Keeping 20 seconds costs little but preserves the failure. A local shared
120-second startup allowance and poller repair is small and reversible, but
genuine missing health remains pending longer. Dynamic progress/heartbeat
extensions require new evidence contracts and cross-process policy, with no
need demonstrated by this report. Rebuilding core would add migration risk.

## 7. Recommended intervention

Use `MANAGED_STARTUP_HEALTH_TIMEOUT_SEC = 120.0` in a services policy module,
consumed by normal launch, transaction, recovery and host defaults. This gives
six times the reported roughly 20-second startup while keeping a finite
two-minute ceiling; it is a conservative policy choice, not a measured maximum
startup bound. Preserve explicit timeout injection for tests and callers.
Read and validate evidence before testing expiry, cap sleep to remaining time,
and ignore stale attempts through the same deadline path. Wrong or unhealthy
matching evidence still fails immediately. Do not emit health early, disable
rollback, extend the independent shutdown wait, or alter installed software.

Completion requires the original repro, normal/recovery default coverage,
architecture and cumulative managed-bundle gate to pass.

## 8. Reversible sequence

Record diagnosis and red tests; centralize defaults; repair the existing
poller; update contracts and acceptance status; run focused and cumulative
verification. Existing public r2 files are immutable. The host is installed
in the stable launcher, so updating only a target bundle cannot change the
old launcher's health budget; delivery needs a freshly built Setup/launcher.

## 9. ADR

Context: a successful handoff exposes startup waiting that is too short and
misses deadline evidence. Decision: services owns a shared finite 120-second
startup policy, platform retains one proof-validating wait loop. Alternatives:
20 seconds, indefinite waiting, progress-extended deadlines. Consequences:
slow startup can finish; actual failed startup still triggers safe rollback.
Review trigger: measured startups approach/exceed 120 seconds, or a new phase
proposes another independent readiness owner or timeout override.

## 10. Uncertainty

The user's timing and rollback success are reported evidence. No raw launch
receipts or monotonic measurements were provided. Source inspection shows
healthy receipt publication only after runtime start succeeds, immediately
before the event loop; it does not show a timer reporting success. Actual
readiness time, settings preservation, reboot and clean-VM acceptance remain
unverified. The repaired source does not change published 3.7.14/3.7.15 bytes.

## Validation and postmortem

The shared services policy is implemented and all four constructor defaults
consume it. The existing lifecycle now takes a final proof sample and bounds
sleep, including stale-attempt waiting. Runtime health publication, preparation
and shutdown budgets, rollback ordering, and artifact schemas are unchanged.

- Focused host/lifecycle/current/recovery/transaction suite: 42 passed, 8.37s.
  This includes every original red repro. Default candidate health at 30s and
  exactly 120s finalizes the update without rollback. Explicit 20s still times
  out, proving caller injection and genuine rollback remain effective.
- No health or late candidate health at 121s: timeout at 120s, restore pointer,
  stop the exact candidate before old launch, wait for the old version's actual
  matching health 30s later, then report `rolled_back`. Late candidate evidence
  does not satisfy the old launch attempt. Both roots remain available.
- Real artifact polling through current launch and interrupted recovery accepts
  a virtual 30-second startup. Direct transaction composition also tolerates
  the same delay. Deadline mismatches/unhealthy evidence fail; stale/missing
  evidence times out without oversleep.
- Cumulative managed-bundle gate: exit 0. Full unit suite 1,989 passed, 64
  integration cases deselected, 69.08s; includes all 56 architecture tests.
  Synthetic 1 passed, 0.24s; loopback HTTPS 2 passed, 1.94s; signed offline
  managed-bundle integration 2 passed, 119.18s. This exercises real offline
  environment construction, signature admission, launch proof, fault/rollback
  matrix and unchanged shared user-data bytes.
- `git diff --check`: passed. No debug instrumentation, installed-app edits,
  public asset mutation, commit or normal-index changes were introduced.

```text
.venv/Scripts/python.exe scripts/run_unit_tests.py -- tests/app/test_managed_update_host.py tests/platform/test_managed_update_lifecycle.py tests/services/test_managed_current_launch.py tests/services/test_managed_update_recovery.py tests/services/test_update_transaction.py -q --tb=short
artifacts/about-health-timeout-20261006/targeted.log
.venv/Scripts/python.exe scripts/verify_managed_update.py --stage managed-bundle
artifacts/about-health-timeout-20261006/managed-bundle-gate.log
```

Root causes: insufficient duplicated startup defaults and an expiry check that
skipped final evidence. Slow-startup tests at every default owner and the exact
deadline regression would have prevented these defects. No alternate readiness
or timeout state owner is necessary. These results validate source behavior,
not a new installed/public release: no new candidate was rebuilt or published
in this repair, and actual About success still requires fresh Setup/launcher
delivery followed by device retest.

Subsequent directly authorized delivery is complete: 3.7.16/3.7.17 rebuilt and
published as `acceptance-20261006-r3`. Both exact offline-installed wheels prove
120-second health defaults, virtual 30/120-second health success, finite missing
health timeout, and retained 600-second preparation. Frozen source tests,
packaged/extraction gates, all 20 public asset identities and anonymous complete
hashes, discovery and downloaded B signature admission pass. See
[publication evidence](github-acceptance-publication-20261006-r3.md).
On 2026-10-06 the user reported「成功了 更新到3.7.17」. Actual device About
update acceptance passed (user reported); event logs and health receipts were
not separately collected for this retest. Settings retention and reboot remain
pending.
