# Update and installation refactor

Scope: release bundle verification and Windows shortcut worker startup. Preserve
automatic update, first installation, recovery, uninstall and publication gates.

## Bundle admission

`VerifiedManagedBundleStager` remains the single owner of compressed identity,
safe extraction, manifest signature/schema, release identity and exact inventory.
Add external artifact verification that owns isolated scratch and returns only
the verified immutable manifest. Migrate build self-verification and final asset
verification to it. Asset provenance must enumerate the exact admitted wheels
and lock; notices, source archives, Setup evidence, acceptance and Authenticode
remain release policy in the asset gate.

Validate authentic signatures and corrupted/missing/extra inventory even when
outer asset hashes are updated. Assert scripts do not extract/read bundle ZIPs.
Scratch cleanup must occur on both acceptance and rejection, without deleting
anything in the source artifact directory. This adds a scratch copy to release
verification; no release speed improvement is claimed for this change.

## Native shortcut phases

`WindowsInstallationIntegration` owns shortcut membership and registry receipts.
The isolated stdlib worker accepts at most three intents in one homogeneous
phase, validates the entire request before native calls, then settles sequentially.
Create Start Menu links in one process, write registry, then create desktop link
in another. Before payload removal, prove all existing owned links in one process.
Immediately before native deletion, run a fresh proof in another process.
Do not cache ownership proofs or combine these lifecycle phases.

Validate malformed/duplicate/mixed requests before mutation, partial worker
failure, modified ownership between proof passes, older desktop receipts and
Unicode paths with an empty PATH. A complete three-link lifecycle uses four
worker launches instead of nine; elapsed savings depend on the host.

## Delivery and rollback

Keep these changes separately reviewable in the diff. Run targeted tests,
architecture tests, the unit suite and native/integration smoke gates. Rollback
requires reverting the adapter and worker protocol together. No version bump,
publication or candidate acceptance is part of this refactor.
