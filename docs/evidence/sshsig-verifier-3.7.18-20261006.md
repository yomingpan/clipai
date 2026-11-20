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
remote execution of that new packaged proof passed in the validation run below.

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

## Follow-up: actual Windows candidate at f637065

Source: `f637065c0df6ea543b20938164297301eedc559f`.
[Windows CI](https://github.com/yomingpan/clipai/actions/runs/37467548051) passed
Python 3.10–3.13 unit/architecture checks.
[Candidate CI](https://github.com/yomingpan/clipai/actions/runs/37467548213) passed
all steps, including the new native bootstrap signature proof, offline installed
imports, full transaction gate and compiled Setup extraction. Official authority
admission was correctly skipped on this isolated branch.

Downloaded artifact `11415718379`: 65,628,602 bytes, verified SHA-256
`711e358d76de6e005c020ba26b9b88fc38667ad21c8683d7ec43447121e683e8`.
Technical Setup: 40,560,101 bytes, SHA-256
`dd4bd8e9526c49448d978cdba41745c0b147c7bc45a9f75a8102650d358bf688`;
actual native inspection returned `NotSigned` with null publisher/timestamp.
Bundle: 24,455,784 bytes, SHA-256
`02da0d2979a6f536a1ac31bfdae08efece9e99d442db476899711485235c74f9`.
Packaged imports were under the installed venv, including cryptography/cffi/
pycparser and `_cffi_backend.cp312-win_amd64.pyd`; editable import was false.

Read-only native review of that exact runtime/wheel set examined **230** files:
125 `NotSigned`, 105 `Valid`, no damaged/untrusted/unknown signature status.
Original third-party bytes were retained. Detailed file hashes and publisher
subjects: `artifacts/official-release-3.7.18/crypto-native-review/native-review.json`.
This is native inventory evidence, not clean VM or user acceptance.

Matching upstream full runtime licensing archive: 43,477,314 bytes, SHA-256
`b7cf8be5cd5222d1e456fbf71257efe558d84fe092757b6892c16584e5df01c2`.
Its `PYTHON.json` identifies 3.12.14 / x86_64-pc-windows-msvc / vcruntime:140;
the actual selected runtime reports OpenSSL **3.5.8 (25 Aug 2026)**. Required
runtime license texts and build metadata are being supplemented into pinned
bootstrap notices. The stripped archive omitted most separate upstream licenses.
Pygame's LGPL filename was also missed by the former basename filter; its exact
2.5.3 source SHA-256 is
`dc04f0bf1a270a84eb371556298a9902b9c4ab08137c9dd10ef03fa4e7fcbfed`.
Notice inclusion/integrity changes have 90 targeted/architecture/workflow passes
so far. Final supplemental notice completeness and fresh packaging remain pending.
