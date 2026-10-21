# Installer release ownership diagnosis

Date: 2026-10-04. Baseline: `a0502d34cfa2b1ab554c480d39b8b8813d1ef201`.

1. **Judgment: Yellow, local refactor, high confidence.** The Preview builder
   rebuilds an app wheel and creates a local key. Reusing it as the tag builder
   would create another artifact/trust owner. This is observed in
   `experiments/first_install/build_preview.py`, not an observed published failure.
2. **Trigger:** P1 requires two entry points to consume one artifact. Release CI
   already owns wheel/lock/bundle assembly and immediately publishes a draft.
3. **Protected behavior:** existing coordinator, gate, stager, materializer,
   retained-data uninstall, offline runtime, production key rejection and
   explicit About intent remain authoritative.
4. **Four-part diagnosis:** `ManagedReleaseBuilder` owns the signed bundle;
   `VerifiedManagedBundleStager` owns admission; `FirstInstallCoordinator` owns
   installation policy. A Setup packaging adapter owns fixed bootstrap inputs
   and packaging only. This is reusable distribution capability. Parsing or
   resolving dependencies in Setup leaks release ownership; source-copying the
   bootstrap leaks checkout contents into an otherwise immutable release.
   Enforce with catalog-bound admission, wheel-derived bootstrap, pinned input
   hashes, substitution tests and CI asset checks.
5. **Debt multiplier:** independent assembly/trust creates drift for each future
   dependency, bootstrap or key rotation change; three such changes require two
   reconciliations each and can silently ship different app bytes.
6. **Options:** keeping Preview unchanged is reversible but unsuitable for CI;
   a bounded packaging adapter costs one seam and tests; replacing the installer
   engine is expensive and threatens verified recovery. Choose the adapter.
7. **Boundary/completion:** accept one bundle/catalog/keyring and pinned runtime,
   verifier/compiler inputs; never build/sign an app bundle in the Setup builder.
   Record wheel/lock/bundle/Setup and source identities. Reject substitutions
   before compilation. Public release additionally requires admitted inputs,
   publisher signing and device evidence.
8. **Sequence:** parameterize the existing wizard without changing Preview
   defaults; add packaging adapter and tests; build an isolated technical
   candidate; run installed-wheel smoke; connect CI with no automatic publish.
9. **ADR:** keep one release payload and one install engine. Setup embeds the
   exact About bundle and takes bootstrap code from its wheel. Alternatives are
   duplicated builders and a new installer engine. Consequence: fixed inputs
   are mandatory and incomplete admission blocks official packaging. Review on
   a second packaging path, bootstrap protocol change or runtime/key rotation.
10. **Uncertainty:** no clean VM/signer/CI permissions confirmed. Existing
    runtime and OpenSSH Preview inputs have not been approved for distribution.
    Next evidence: candidate assembly/import proof and explicit input admission.
