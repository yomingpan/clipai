# ClipAI 3.7.21 public release evidence

Date: 2026-10-27 (Asia/Taipei). Published as latest:
[ClipAI 3.7.21](https://github.com/yomingpan/clipai/releases/tag/v3.7.21).
GitHub release ID: `424484641`.

## Source and automated validation

- Annotated tag `v3.7.21` pins `23ecbc9955a715b230f7452fefd8273ba4388248`.
  Only the release tag was pushed.
- Local verification: 2,493 unit tests, 65 separately run architecture tests,
  both official language packs and 20 real Windows UI integration tests passed.
  UI tests cover Entry Panel, input recovery and Inline pill rendering/focus.
- [Windows Python 3.10–3.13 CI](https://github.com/yomingpan/clipai/actions/runs/40356348202)
  passed in all four supported versions.
- [Official build and compiled installer cycle](https://github.com/yomingpan/clipai/actions/runs/40356348272)
  passed. Both actual desktop startups passed without a user-app-running skip.
  Installation, duplicate-install rejection, active-process removal rejection,
  broken-venv removal, retained-data reinstall, final removal and settlement passed.
- Official artifact `12666541919`: 73,214,796 bytes, SHA-256
  `9858751e1f7b76e82644dcba46ce9a94e29b71239d5b2e5496bea6024cd29522`.
  Downloaded bytes were checked against this GitHub identity before extraction.
- Canonical Bundle admission passed production signature, version, complete
  inventory and wheel/lock provenance. Production keyring and approved build
  inputs are unchanged; all 41 dependency wheel contents and 113 notice files
  match 3.7.20.

## Final identities and publication

- Setup: `ClipAI-Setup-3.7.21-windows-x64.exe`, 40,632,408 bytes, SHA-256
  `9bb0d3960dfeff2bb46da836935e46536d3eed6eb4b0290641312ce263a45acb`.
- Bundle: `clipai-managed-3.7.21.zip`, 24,481,766 bytes, SHA-256
  `186a724b0065ed57e6f3077ae546fa0375d574266ad32a796aba6c54ec9ff902`.
- Real Setup Authenticode inspection returned `NotSigned`; managed content
  retains production Ed25519 signatures.
- All nineteen draft assets were checked against prepared filenames, sizes and
  GitHub SHA-256 digests before publication as latest.

## Version-specific acceptance

The maintainer explicitly instructed: “接受，通過自動驗證後公開揭露並發布”.
The question and decision explicitly cover 3.7.21, unsigned Windows Setup and
pending independent clean Windows 11 standard-user, reboot/cross-logon,
failure-recovery, browser/Windows trust and first-user observations.

`acceptance.json` binds that decision to the final Setup and Bundle hashes.
These independent gates remain pending; the public description and release
notes disclose them. The default readiness verifier still rejects pending
required acceptance. No production gate was weakened or relabeled as passed.

## Public delivery verification

Anonymous GitHub reads confirmed 3.7.21 is latest, not draft or prerelease.
All nineteen assets were anonymously downloaded and their full sizes and
SHA-256 hashes matched the prepared identities. The downloaded Bundle passed
production signature and canonical inventory/provenance admission; downloaded
Setup Authenticode returned `NotSigned`.

The actual `HttpsManagedReleaseSource` with `UrllibManagedUpdateTransport`
discovered 3.7.21 from the official latest catalog for installed app 3.7.20 and
stable launcher 3.7.18. This verifies the production discovery path; it does not
claim an installed-device About interaction or independent device acceptance.

Raw evidence is retained under `artifacts/official-release-3.7.21/`, including
`ci-checkpoint.json`, `draft-release-metadata.json`, `expected-public-assets.json`,
`release-readiness.json`, `release-checkpoint.json`,
`postpublication-download-proof.json` and `postpublication-catalog-proof.json`.
