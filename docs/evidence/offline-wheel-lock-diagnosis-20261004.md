# Offline wheel hash diagnosis

1. Judgment: Green; local change at the existing managed-release builder owner.
   High confidence in source/built-wheel hash mismatch; remote original repro
   must pass after the change before declaring the complete CI gate passed.
2. Evidence: candidate run `37208472184` built Setup then failed packaged offline
   installation. PyPI lock admits langdetect 1.0.9 source hashes `7cbc0746…` /
   `cbc1fef8…`; the admitted local built wheel hash is `940310f4…`.
   `artifacts/offline-lock-repro-20261004/red.txt` proves offline pip rejects that
   exact pattern. The same dry-run with actual wheel hashes passes (`green.txt`).
3. Protect pinned source admission, version resolution, offline hash checking,
   one wheelhouse/managed bundle, signature verification and Setup identity.
4. Ownership: managed-release builder seals the install lock; CI composes its
   existing CLI. Source resolution/build admission and the finished install
   artifact are distinct identities, not two runtime update mechanisms. No
   knowledge crosses into UI or services. Tests reject missing/extra/wrong-version
   or duplicate wheels and an unhashed source lock; the actual installed-wheel
   smoke remains the enforceable complete gate.
5. Debt multiplier: bypassing `--require-hashes` or hashing files independently
   in each Setup/About workflow would grow three incompatible trust policies.
6. Options: binary-only downloads (cannot support source-built dependencies),
   disable hash checks (unacceptable), seal concrete built bytes after verified
   source builds (bounded, preserves all current consumers).
7. Recommendation: existing builder CLI adds `--seal-wheelhouse-lock`, verifies
   the resolved package name/version set, and hashes the actual completed wheels.
   Python 3.12 Windows markers use the pinned runtime profile. Retain source and
   build locks as provenance; only the sealed lock enters the managed bundle.
8. Migration: preserve hash-checked `pip wheel` input as build-requirements.lock,
   seal requirements.lock once afterwards, package it, and rerun the original
   remote packaged-app/extraction gate. No dependency re-resolution at sealing.
9. ADR: one owner, successive source and output artifact stages. Review when
   runtime/ABI/marker profile changes or another builder starts sealing locks.
10. Limits: minimal wheel dry-run isolates the hash defect; it does not replace
    full dependency installation, runtime imports, About update or VM acceptance.

Ranked hypotheses: source vs built-wheel hash; missing resolved wheel; wrong ABI.
The first reproduced with one real dependency before the fix. No debug logging
or hash-verification bypass was added to installed production code.
