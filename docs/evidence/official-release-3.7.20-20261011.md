# ClipAI 3.7.20 public release evidence

Date: 2026-10-11. Published as the latest official release:
[ClipAI 3.7.20](https://github.com/yomingpan/clipai/releases/tag/v3.7.20).
GitHub release ID: `409759519`.

## Source and completed validation

- Annotated tag `v3.7.20` pins `bc1d7f8575f0ae6a6ece9cfcf3be6de5049f28b4`.
  Only the release tag was pushed; main and develop were not pushed.
- [Windows Python 3.10–3.13 source/unit/architecture CI](https://github.com/yomingpan/clipai/actions/runs/38150809496)
  passed in all four supported versions.
- [Official build and compiled Setup cycle](https://github.com/yomingpan/clipai/actions/runs/38150809493)
  passed. Both actual desktop startups passed without a user-app-running skip.
  Installation, duplicate-install rejection, active-process removal rejection,
  broken-venv removal, retained-data reinstall, final removal and settlement passed.
- Local feature verification passed 2,160 unit tests and 62 architecture tests,
  with real Windows UI smokes for both Popup and Inline positions and Entry Panel.
  Release preparation passed 14 tooling tests and both language packs.
- Official CI artifact `11706826339`: 73,176,259 bytes,
  SHA-256 `dbd657db66e258c780b17efa77a3342d532b087aa2b805423c89c47819ebe749`.
- Canonical Bundle admission passed production content signature, schema,
  version, exact inventory and complete wheel/lock provenance checks. Approved
  build inputs and production keyring match 3.7.19; all 41 dependency wheel
  contents and 113 notice files match that version.

## Published identities and policy

- Setup: `ClipAI-Setup-3.7.20-windows-x64.exe`, 40,601,690 bytes,
  SHA-256 `d4ff64b94cd2da7cd68a3007d2b23032f5c5adda9af6a9207a97436f5c8b3924`.
- Bundle: `clipai-managed-3.7.20.zip`, 24,461,318 bytes,
  SHA-256 `be1a8bf89e4c85c08c512674c6b8179dda6ac1307819265addcaf62ff118bda5`.
- Setup publisher policy is unsigned. Real Authenticode inspection returned
  `NotSigned`; managed content retains production Ed25519 signatures.
- All nineteen draft assets were inspected against exact prepared filenames,
  sizes and GitHub-reported SHA-256 digests before publishing as latest.
- Existing official installations with stable launcher 3.7.18 can receive
  the app update through About. App updates retain the installed launcher and data.

## Explicitly accepted acceptance gaps

After exact final CI and asset validation, the maintainer instructed:
“接受並公開揭露缺口，發布 3.7.20”. This decision applies only to this exact 3.7.20 candidate.

Independent clean Windows 11 standard-user cycle, final-device failure recovery,
reboot, cross-logon behavior, browser/Windows trust observations and first-time-user
results remain **pending**. The public description, `RELEASE_NOTES.md` and
`acceptance.json` disclose these gaps and exact candidate identities.

The default release-readiness gate still rejects pending required acceptance.
No production gate was weakened and no pending status was relabeled as passed.
Publication uses the maintainer's explicit version-scoped acceptance; content
signature, exact asset identity and native/license admission remain required.

## Public delivery verification

Anonymous GitHub API reads confirmed this release is latest, not draft and not
prerelease, with all nineteen expected names, sizes and SHA-256 digests. All
nineteen assets were anonymously downloaded and their complete byte hashes
matched the prepared identities. Large assets used bounded HTTP ranges and
were reassembled before hashing.

Canonical admission of the downloaded Bundle passed production signature,
schema, version, exact inventory and complete wheel/lock provenance checks.
Downloaded Setup Authenticode inspection returned `NotSigned`; notices and
corresponding source admission passed. The production keyring is unchanged.

The actual `HttpsManagedReleaseSource` with `UrllibManagedUpdateTransport`
discovered 3.7.20 from the official latest catalog for installed app version
3.7.19 and stable launcher 3.7.18. No installed-device About action was
simulated or claimed; independent device/user acceptance remains pending.

Raw evidence is retained under `artifacts/official-release-3.7.20/`, including
`ci-checkpoint.json`, `draft-release-metadata.json`, `public-release-metadata.json`,
`postpublication-download-proof.json`, `postpublication-catalog-proof.json`,
`release-readiness.json` and `release-checkpoint.json`.
