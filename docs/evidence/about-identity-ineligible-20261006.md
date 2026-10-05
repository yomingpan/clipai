# About identity_ineligible：Windows venv redirector

日期：2026-10-06，Asia/Taipei。使用者實際測試 A 3.7.10 → B 3.7.11。

## Reproduction and facts

Transaction `update-a9579db369134fc9942b55633a4feaa7` request names current
3.7.10, target 3.7.11, PID 11968 and logical executable
`versions/3.7.10/.venv/Scripts/python.exe`. Its result at
`2026-10-05T16:06:55.845209+00:00` is failed / identity_ineligible / active 3.7.10.
No journal or handoff-ready artifact was present; the install pointer was revision
0, current 3.7.10, previous null. No installed file or setting was modified by
the diagnosis, and no user process was stopped.

A read-only call of `WindowsManagedProcessHandle` with that request's exact
PID/executable failed with `installed process executable does not match request`.
The same PID's Windows image was `ClipAI Candidate/runtime/python.exe`, running
the explicitly supplied acceptance helper. This was not PID reuse or a wrong
catalog. The request B hash is
`33844a885d107f1321c65394f63ccfb6ffc18d64c98756be3537669ba6331ec3`.
The actual 3.7.10 `pyvenv.cfg` home is the owned install's runtime directory.

CPython [venv documentation](https://docs.python.org/3.12/library/venv.html)
and [redirector implementation](https://github.com/python/cpython/blob/main/PC/venvlauncher.c)
confirm that Windows venv launchers locate the original interpreter through
`pyvenv.cfg` home. Native process image and logical `sys.executable` are distinct.

## Diagnosis before the bounded repair

1. **Judgment:** Yellow, local refactor, high confidence. A valid Windows
   execution mechanism was modeled as direct path equality. Reproduce at the
   OS seam before changing identity policy.
2. **Trigger:** Repeated About blockers require diagnosis. The live exact-PID
   check is red; a native agent-owned venv test reproduces the same inequality.
   GUI text alone does not prove which identity stage rejected the request.
3. **Protected behavior:** Signed current installation, exact logical venv
   identity, retained same-PID handle, foreign-process rejection, exact B bytes,
   readiness-before-shutdown, user data and atomic active pointer.
4. **Ownership:** `ManagedInstallLayout` owns logical/signed install proof;
   `WindowsManagedProcessHandle` owns native process-image verification and
   retained handle lifetime. Venv image translation is reusable OS capability,
   not a helper-specific exception. The host composes the explicit base runtime;
   core request and UI retain logical identity. Native regression and negative
   image/config tests enforce the boundary.
5. **Multiplier:** Treating logical identity as OS image hides platform
   semantics. More update, shutdown and recovery fixes would duplicate
   executable exceptions without this single translation owner.
6. **Options:** A broad python.exe allowlist loses identity. A request schema
   migration is larger and does not prove its new field. A bounded adapter
   mapping removes the observed error while retaining the existing protocol.
7. **Intervention:** Prove logical layout before opening the process; accept
   only the explicit base image paired with the exact venv's contained absolute
   home. Unknown/foreign cfg or image remains ineligible. No installed patches,
   key replacement, latest changes, PID substitution or automatic update.
8. **Sequence:** Red live check; failing adapter regression; repair adapter
   and host; native Windows process test; targeted/unit/architecture/bundle gates;
   fresh immutable A/B builds; separate publication authorization and actual
   attended acceptance.
9. **ADR:** Keep logical and physical identities distinct at the OS adapter;
   keep request schema and launch-health identities unchanged. Review again if
   another runtime mechanism cannot be proven by this venv mapping.
10. **Uncertainty:** The fixed source must be built into a new stable launcher.
    Current published 3.7.10 does not acquire the fix from a newer B bundle.
    No actual updated-version success is claimed until attended testing.

## Validation and candidate status

`python scripts/run_unit_tests.py -- tests/platform/test_managed_process.py
 tests/app/test_managed_update_host.py -q`: 11 passed.
`python scripts/run_unit_tests.py -- tests/platform/test_managed_process.py
 -m integration -q`: 1 real Windows native regression passed. It first verifies
that exact logical-image equality rejects the process and then validates the
same retained PID through its explicit runtime mapping and normal exit.

Full managed-bundle gate passed: 1,964 unit (architecture included), synthetic 1, real HTTPS/signature 2, signed managed-bundle 2. After preserving signature-failure reporting, the final 13 targeted process/host cases passed; final full unit confirmation is running. Fresh source-bound 3.7.12 / 3.7.13 candidates
are being prepared; they are not published, installed or user-accepted.
