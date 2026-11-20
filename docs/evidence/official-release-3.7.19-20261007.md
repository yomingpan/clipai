# ClipAI 3.7.19 public release evidence

Date: 2026-10-07. Published at 22:03 Asia/Taipei as the latest official release:
[ClipAI 3.7.19](https://github.com/yomingpan/clipai/releases/tag/v3.7.19).
GitHub release ID: `405826411`.

## Source and completed validation

- Annotated tag `v3.7.19` pins `dbb2b5a7f897a71337b573eb89b95ff8401dc343`.
  The release tag was pushed without pushing main or develop.
- [Official build and compiled Setup cycle](https://github.com/yomingpan/clipai/actions/runs/37622334467)
  passed. Both actual desktop startups passed without a user-app-running skip.
  Installation, duplicate-install rejection, active-process removal rejection,
  broken-venv removal, retained-data reinstall, final removal and settlement passed.
- [Windows Python 3.10–3.13 matrix](https://github.com/yomingpan/clipai/actions/runs/37622334611)
  passed. Local refactor validation passed 2,055 unit/architecture tests and five
  integration tests; version packaging passed 24 tests and two language packs.
- Downloaded official CI artifact `11482643095`: 73,160,766 bytes,
  SHA-256 `e3b33443b8006daf46e9787fed863b88552d09b44235e8d8a5c5f2b75b283adc`.
- Canonical Bundle admission passed signature, schema, version and exact inventory
  checks. The production trust key and approved build inputs match 3.7.18.
  All 41 dependency wheel contents and 113 notice files match the previous release.

## Published identities and policy

- Setup: `ClipAI-Setup-3.7.19-windows-x64.exe`, 40,597,463 bytes,
  SHA-256 `13a21404add343f9a2bdd9362548d6950571a5aaa860cb6a51e891945cb199ff`.
- Bundle: `clipai-managed-3.7.19.zip`, 24,458,287 bytes,
  SHA-256 `9902c1b2a7120742067c6223affcd4a268e44418ec92b589f0a65158702d684c`.
- Setup publisher policy is unsigned; real Authenticode inspection returned
  `NotSigned`. Managed content retains production Ed25519 signatures.
- Existing official launcher 3.7.18 can receive the app update through About.
  App-only updates retain the installed stable launcher and Setup engine.
  The shortcut batching improvement applies to the new Setup engine.
- Nineteen uploaded assets, including acceptance, provenance, checksums, notices,
  corresponding source and compiled-cycle evidence, have exact GitHub-reported
  sizes and SHA-256 digests matching the prepared files. GitHub also generates
  two source archives, which are not part of the nineteen uploaded assets.

## Explicitly accepted acceptance gaps

After exact final CI and asset validation, the maintainer instructed:
“接受並公開揭露缺口，立即發布 3.7.19”. This decision applies only to 3.7.19.

Independent clean Windows 11 standard-user cycle, final-device failure recovery,
reboot, cross-logon behavior, browser/Windows trust observations and first-time-user
results remain **pending**. The public release description, `RELEASE_NOTES.md`
and `acceptance.json` disclose these gaps and record the exact candidate identities.
CI results do not substitute for those independent observations.

The default release-readiness gate still rejects pending required acceptance.
No production gate was weakened or pending status relabeled as passed. Publication
uses the maintainer's explicit version-scoped acceptance of the disclosed gaps;
content signature, asset identity and native/license admission remain required.

## Public delivery verification

Anonymous GitHub API reads confirmed `v3.7.19` is latest, not draft and not prerelease,
with all nineteen expected filenames, sizes and SHA-256 digests. All nineteen
assets were anonymously downloaded and their complete byte hashes matched the
prepared identities. Large assets were downloaded through bounded HTTP ranges
and reassembled before hashing.

Canonical admission of the downloaded Bundle passed production Ed25519 signature,
schema, version, complete file inventory and exact wheel/lock provenance checks.
Downloaded Setup Authenticode inspection returned `NotSigned`; downloaded notices
and corresponding source admission passed. The production keyring remains unchanged.

The actual `HttpsManagedReleaseSource` with `UrllibManagedUpdateTransport` discovered
3.7.19 from `https://github.com/yomingpan/clipai/releases/latest/download/catalog.json`
for installed version 3.7.18 and launcher 3.7.18. No installed-device About action
was simulated or claimed. Default complete device acceptance remains incomplete.

Raw local evidence is retained under `artifacts/official-release-3.7.19/`:
`public-release-metadata.json`, `postpublication-download-proof.json`,
`postpublication-catalog-proof.json`, `release-checkpoint.json`,
`release-readiness.json` and `public-release.jpg`.
