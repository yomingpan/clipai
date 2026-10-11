# SSHSIG verifier diagnosis and migration

Date: 2026-10-06. Scope: the necessary verifier input for official 3.7.18 Setup.

## 1. Judgment

Yellow; recommend an incremental migration at the existing platform adapter.
Confidence: high for the boundary, pending interoperability and packaged tests
for the implementation. The pinned Win32-OpenSSH archive is explicitly
[Preview/non-production](https://github.com/PowerShell/Win32-OpenSSH/releases/tag/10.0.0.0p2-Preview),
which blocks the documented official input admission. Do not relabel it.

## 2. Evidence

`update_signature.py` already owns canonical-manifest/key/namespace verification.
`VerifiedManagedBundleStager` and `ManagedInstallLayout` consume a verifier port.
Concrete executable knowledge also appears in main composition, first-install
backend/selfcheck, Setup builder, CLI inputs and acceptance tools. This dependency
prevents shipping the official installer despite passing functional tests.
Upstream package availability is evidence; it does not prove a new adapter correct.

## 3. Protected capability

Verify existing OpenSSH Ed25519 SSHSIG envelopes over canonical JSON, with the
same production keyring and namespace, bounded input, rejected test authority,
tampering rejection and operation-scoped existing installation/update recovery.
Signing stays with the existing build-time OpenSSH signer. No key rotation,
format change, new update channel, new installer or new workflow owner.

## 4. Four-part diagnosis

- Owner: `Ed25519ManifestVerifier` in platform owns signature admission; stager
  owns bundle admission; app composes; build pipeline owns exact wheel bytes.
- Capability: portable verification is reusable across install, update, selfcheck
  and build self-verification, rather than an unsigned-release exception.
- Propagation: private `ssh-keygen.exe` locations/PATH/work directories leak into
  callers that only need manifest verification. Windows publisher policy is separate.
- Enforcement: real OpenSSH interoperability, historical bundle verification,
  negative protocol tests, no subprocess/PATH dependency, bootstrap dependency
  extraction and installed-wheel smoke, plus architecture/full transaction gates.

## 5. Debt multiplier

Retaining the executable policy would require each later verifier upgrade,
platform port or maintenance change to edit composition, CLI and bootstrap in
parallel. Three such changes would multiply pin and missing-tool failure paths.
Keep one adapter and one exact managed wheelhouse as the source of truth.

## 6. Options

Accept Preview temporarily: low effort but conflicts with current production
admission and inherits unsupported runtime tooling. OS OpenSSH: removes bundled
Preview but adds a machine prerequisite/version/PATH dependency. Replace the
adapter backend: moderate work and a bounded binary envelope parser; retains
wire compatibility and uses a production library in the existing sealed lock.
Core rebuild: unnecessary and substantially less reversible.

## 7. Intervention

Use [cryptography 50.0.2](https://pypi.org/project/cryptography/50.0.2/) for the
Ed25519 primitive, pinned in Windows constraints and sealed in each bundle's lock.
Parse only SSHSIG v1/Ed25519/sha256 or sha512 with bounded lengths; retain trusted
key and namespace equality and canonical JSON. Follow the
[OpenSSH envelope and signed-data protocol](https://github.com/openssh/openssh-portable/blob/master/PROTOCOL.sshsig).
Ship its exact admitted wheels/dependencies in bootstrap, with notices and native
inventory. Remove the runtime OpenSSH archive/tool prerequisite. No custom crypto
primitive, silent fallback, provider/UI change or publisher signing service.

## 8. Reversible sequence

Add protocol/interoperability coverage; replace the adapter backend and callers;
change Setup bootstrap/pins/CI together; verify historical signatures and new
complete transaction/package tests; commit coherently; produce fresh candidate.
Before a public tag, reverting this commit restores the previous technical path.
Do not promote previous branch artifacts, which lack the new dependency/host.

## 9. ADR

Context: an unsupported bundled executable blocks formal distribution.
Decision: retain the verification owner/port/wire format and replace its backend
with a sealed production cryptography wheel. Alternatives: Preview waiver, OS
dependency, broad rewrite. Consequences: a small audited envelope parser and
additional bootstrap wheels, no verifier process or PATH/runtime archive.
Review trigger: protocol/key algorithm change, library security advisory or native
wheel/runtime ABI change. Runtime updates remain a Setup maintenance responsibility.

## 10. Uncertainty

Actual wheel/platform compatibility, transitive bootstrap imports, historical
SSHSIG interoperability, native/license inventory and final device acceptance
must be verified. Library production classification does not complete those gates.
