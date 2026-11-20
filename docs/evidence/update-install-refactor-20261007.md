# Release admission and shortcut batching evidence

Baseline: `60538ce`. Scope and rollback are recorded in
[the implementation plan](../specs/update-install-refactor-plan-20261007.md).

## Result and ownership

Build self-verification and final asset verification now use the same complete
`VerifiedManagedBundleStager` admission as installation and managed update.
The release scripts no longer extract archives or implement partial ZIP
verification. Signature, schema, release identity and exact inventory have one
owner. Release-specific provenance, source/notices, Setup evidence, device
acceptance and final Authenticode policies retain their existing owner.

`verify_external` owns a temporary transaction, copies the source artifact,
uses existing admission and returns only its immutable manifest. The final
asset gate compares provenance to catalog identity instead of separately
hashing the bundle twice. Complete verification adds payload extraction/hash
and a scratch copy; overall release gate latency has not been measured.

Windows integration now collects its Start Menu membership once. The isolated
stdlib Shell Link worker admits the whole bounded homogeneous phase before COM
operations. A three-link create/uninstall lifecycle launches four workers:
Start Menu creation, desktop creation after registry, pre-payload ownership
proof, and a fresh pre-native-deletion proof. No proof is cached. COM apartment
and link lifetimes remain per link, avoiding shared mutable COM state.

This slice concentrates validation and reduces duplicated rules/process
startup. It is not a net source-line reduction: bounded batch validation and
external scratch ownership add code. The preceding refactor removed 183 net
code/tooling lines; this slice adds about 31 production/tooling lines, with
additional regression tests. No broad rewrite or second lifecycle owner was
introduced.

## Measured shortcut cost

Five alternating samples per mode on this Windows host, using real COM links,
isolated Python and an empty PATH. The reference uses one intent per worker
with the current worker; the batch uses two creation phases and two fresh
proof phases. Registry and payload operations are excluded. Unit tests were
also running, so these are local process-phase measurements, not complete
installer or CI release times.

| Mode | Worker launches | Median seconds | Samples seconds |
| --- | ---: | ---: | --- |
| One intent per worker | 9 | 5.869 | 5.869, 7.057, 6.227, 4.859, 4.756 |
| Phase batches | 4 | 3.057 | 3.772, 2.560, 3.251, 3.057, 1.940 |

Median measured reduction: 47.9%. Raw local evidence is
`.clipai-test-artifacts/shortcut-batching-benchmark.json`.

## Safeguards

- Real OpenSSH signatures pass final asset admission without verifier mocks.
- Invalid signature, changed/missing/extra payload fail even after outer
  catalog/provenance hashes are rebound to the modified archive.
- Incomplete wheel provenance fails; existing signed/unsigned publication
  and device acceptance policies remain covered.
- External scratch is removed on both pass and failure; an existing
  `verified-bundle/user-file` in the assets directory survives.
- Malformed, empty, oversized, duplicate and mixed worker requests cause no
  COM call. A partial Start Menu phase failure cannot publish registry/desktop.
- Changed ownership after the first proof blocks the second; backend failure
  retains retry ownership and shared user data after payload removal.
- A real Unicode pair round-trips target/arguments, rejects changed arguments
  and leaves link bytes unchanged. No PATH lookup or Shell Link Resolve occurs.
- Architecture tests prevent release scripts from reclaiming ZIP extraction
  or verification ownership.

## Validation

Targeted regression/architecture run: 116 passed before the additional backend
and partial-phase failure tests. Native Unicode integration: 1 passed.
Final complete harness:

```powershell
$env:CLIPAI_TEST_TEMP_ROOT = Join-Path (Get-Location) '.clipai-test-artifacts'
.venv/Scripts/python.exe scripts/verify_managed_update.py --stage managed-bundle
```

- Unit/architecture/synthetic suite: 2055 passed, 65 integration tests deselected,
  115.63 seconds.
- Loopback HTTP smoke: 2 passed, 1.78 seconds.
- Real managed bundle installation/update/recovery matrix: 2 passed,
  120.44 seconds.
- Separate native Unicode Shell Link integration: 1 passed, 2.92 seconds.
- `git diff --check`: passed.

No new compiled Setup or clean-VM/device acceptance was produced by this
refactor. Existing release acceptance remains bound to its original candidate;
publishing a new candidate still requires the documented release gates.
