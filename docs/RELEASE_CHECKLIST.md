# Release checklist

Status (2026-10-04): candidate build tooling is implemented. Public release is
**NO-GO** until input admission, the selected publisher policy and device/user gates pass.
See [readiness plan](specs/installer-release-readiness-plan.md),
[runbook](testing/installer-release-readiness-runbook.md) and
[evidence](evidence/installer-release-readiness-20261004.md).

2026-10-06: r3 About acceptance passed by user report. Official candidate
preparation is planned in [the current release plan](specs/official-release-plan-20261006.md).
The maintainer explicitly selected unsigned Windows Setup for 3.7.18 on 2026-10-06.
Managed content signatures remain required. Fixed input admission is approved
after the recorded native/license/compiled-notice proof. Final official asset and
device/user gates remain outstanding; no paid certificate or signing service is needed.

1. Choose a new comparable app version; update `pyproject.toml` and release notes.
   Query the existing release/tag first. Never reuse or move a published tag, or
   replace a version's assets with different bytes. `r4` is a build ID, not an
   upgrade version. Do not promise Preview keyring compatibility with official
   installs; retained-data uninstall/reinstall is the maintenance path.
2. Review constraints on Windows, validate official language packs, and run the
   supported Python 3.10–3.13 source/unit/architecture CI. The managed release
   wheelhouse uses Python 3.12 and a separately generated hashed lock.
3. Review `packaging/windows/setup-inputs.json`: fixed runtime CPython/ABI,
   verifier and compiler archive identities, all compiler component hashes,
   native inventories/notices/licenses, prerequisites, maintenance owner and
   commercial tool eligibility. Current fixed inputs are **approved** with evidence
   in the component review and machine-readable admission record. 3.7.18 selects
   cryptography 50.0.2 from the sealed bundle for SSHSIG verification and removes
   the runtime OpenSSH Preview archive; bootstrap dependency/native import and
   interoperability proofs are required. Never approve by changing a status string alone.
4. Confirm managed content-signing configuration exists without reading secrets:
   secret `CLIPAI_MANAGED_UPDATE_PRIVATE_KEY`, vars `CLIPAI_MANAGED_UPDATE_KEY_ID`
   and `CLIPAI_MANAGED_UPDATE_TRUSTED_KEYRING`. Retain rotation keys and prohibit
   test/local authorities for official packaging. Ed25519 content trust is
   distinct from Windows publisher trust.
5. With direct authorization, create/push an annotated `v{version}` tag only at
   the tested commit. Do not push tags merely to explore tooling. Tag CI builds
   wheel/sdist once, derives one hashed lock/wheelhouse, signs/self-verifies one
   managed bundle, and packages that existing bundle into Setup. It keeps the
   complete managed-update gate and runs packaged import/native extraction and
   asset checks. It has read-only repository permissions and uploads candidates;
   it does not create or publish a GitHub Release.
   Before that, `release-validation/**` branches run the same technical build
   using a disposable `local-validation-*` authority without official secrets.
   Those per-run keys cannot authorize an update to an older candidate. Use an
   explicitly paired A/B local authority for isolated update acceptance; never
   promote branch artifacts or treat their intended tag URLs as published.
6. Validation-branch CI uses `--technical-candidate` and isolated ClipAI Candidate
   identity. Tag CI uses official ClipAI identity and requires reviewed input
   admission; local validation authorities are rejected. Branch artifacts cannot
   be promoted. After reviewed admission, use official mode and a fresh version,
   not a relabeled technical candidate. `build_setup_release` proves the actual
   Git tag/commit and complete first-party wheel/payload source correspondence.
7. Record the publisher policy in exact-hash acceptance. For 3.7.18 use
   `publisher_policy: "unsigned"` and verify the final Setup is actually `NotSigned`.
   Disclose unknown publisher / Windows prompts in the release notes. This policy
   does not waive native/license admission or device gates. For a signed release,
   use the legally available signer, validate upstream/final native admission
   including Python venv redirectors, then sign/timestamp final Setup. Reseal
   provenance/evidence for the changed final hashes; repeat compiled extraction
   and all affected VM/acceptance gates. Never send signing credentials or store
   them in repository, logs or bundle. Never label an unsigned file publisher-signed.
8. Restore a clean Windows 11 x64 standard-user snapshot and execute A installation
   → offline launch after Setup/temp cleanup → reboot → explicit About update B
   (B actually newer) → reboot → retained-data uninstall/reinstall. Use an isolated
   HTTPS catalog via the existing composition seam, not production latest or a
   relaxed keyring. Record normal/fault, cross-logon gate and space/time evidence.
9. Download the final hash through a browser; record Windows trust and
   first result observations from a few new users. No disabling protections or
   substituting an editable test, empty PATH or fixture for a clean VM.
10. Retain the complete asset set: wheel/sdist, `ClipAI-Setup-{version}-windows-x64.exe`,
    `clipai-managed-{version}.zip`, `catalog.json`, public keyring, lock, notices,
    provenance, packaged/extraction proofs, corresponding source archives and
    exact-hash acceptance. Corresponding source bytes must match the input pins.
    The runner's compiled-install/retained-data cycle receipt is also retained;
    it does not substitute for independent device/user gates. Catalog
    names the immutable tag URL; Setup's extracted bundle hash must equal it.
11. Before any directly authorized public promotion, run:

    ```powershell
    python -m scripts.verify_release_assets --assets <final-assets> --require-release-ready --acceptance <exact-hash-acceptance.json> --publisher-policy unsigned
    ```

    All runbook gates must say passed for those exact Setup/bundle hashes, and
    the tool checks the final file's real `NotSigned` status and the recorded
    unsigned policy. Signed policy additionally requires `--publisher` and a
    valid matching publisher/timestamp. A missing
    asset, wrong URL/version/hash or stale evidence rejects the candidate. A draft
    cannot serve ordinary About latest. Create a complete draft only after the
    gate, inspect it, and publish with direct authorization. The maintainer has
    authorized the 3.7.18 release; do not request the same permission again.
    Repository protections remain in effect.
12. After actual authorized publication, verify anonymous HTTPS asset access and
    one installed-app update against the official latest endpoint. Retain old
    version/shared data and compare identities. A candidate-only run leaves this
    gate pending.

This workflow does not publish to PyPI. VM/signer availability and GitHub runner
execution remain independently recorded evidence, not assumptions from local CI
configuration or successful candidate assembly.
