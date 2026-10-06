# 3.7.18 SSHSIG verifier migration evidence

Date: 2026-10-06. Not a public release or completed distribution admission.
Design and required safeguards: [diagnosis / ADR](../specs/sshsig-verifier-migration-3.7.18.md).

The existing platform adapter now verifies SSHSIG v1 with cryptography 50.0.2,
retaining canonical JSON, trusted key ID/public key, namespace and test-key policy.
It supports SHA-256/SHA-512 and rejects malformed/truncated/trailing envelopes,
substituted keys, invalid signatures, wrong namespace and unsupported profiles.
Runtime callers have no executable/PATH/environment/work-root verification policy.
OpenSSH remains the existing build-time signer.

Setup selects the app, packaging, cryptography, cffi and pycparser wheels only from
the admitted managed bundle, enforces the fixed verifier profile/version and
extracts them into bootstrap. The runtime OpenSSH archive/EXE/DLL is removed from
current Setup inputs, fetch and backend copying. Installed/isolated bootstrap
smoke now imports native dependencies and verifies the actual signed manifest;
remote execution of that new packaged proof remains pending.

## Actual verification

- Targeted migration/composition/Setup/workflow tests: 72 passed, 16.38 seconds.
- Final full unit/architecture suite: **2,008 passed**, 64 deselected, 95.95 seconds.
- Architecture suite separately: 56 passed, 5.69 seconds. The initial full run
  had one obsolete assertion expecting the removed OpenSSH archive extraction;
  its safeguard now admits only wheel extraction at Setup and retains the single
  signed-bundle admission owner. It was fixed before the final full pass.
- Real managed loopback/bundle/recovery integration: **4 passed**, 134.09 seconds.
- Real OpenSSH-produced SHA-512 and SHA-256 signatures interoperate. Runtime
  verification succeeds while subprocess spawning is explicitly forbidden.
- Existing r3 B: version 3.7.17, bundle SHA-256
  `a49a5052aa72900e881864d15830b600af471063f938727a10a616982c7803ca`,
  `local-acceptance-pair-acbb91b2bdeb44d89e3fd921c6e49b3d`: stager actually admitted.
- Existing 3.7.18 validation bundle SHA-256
  `6e06ee8847461854133779a122bd8dae3ff402d5b818a127f0c11187e6f74de7`,
  `local-validation-37463625043-1`: stager actually admitted.
  Neither isolated authority is used for the official release.
- Historical verification output:
  `artifacts/official-release-3.7.18/crypto-historical-proof-final/proof.json`.

Local dependency setup initially encountered a recursive pip certificate hook.
An attempted Python `-S` workaround wrote 50.0.2 to Codex's shared runtime instead
of the project venv. The shared runtime's observed original 50.0.1 was restored,
only the newly introduced 50.0.2 metadata was removed after exact path/version
checks, and both code/metadata now report 50.0.1. Project code/metadata report
50.0.2 under `.venv/Lib/site-packages`. Certificate verification remained enabled.

Next gates: new Windows matrix/candidate build and isolated bootstrap native
imports, actual component/native/license review and any required notices, then
official-mode/tag authority and final exact-hash device acceptance/publication.
