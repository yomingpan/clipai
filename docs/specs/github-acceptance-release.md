# GitHub acceptance release: 3.7.8 → 3.7.9

Authorized by the user and published as an experimental prerelease. GitHub Release assets provide both anonymous
Setup downloads and the existing HTTPS About catalog/bundle transport. The user
requested GitHub as the distribution location. No additional hosting service is
required. Public final/stable publication remains a separate authorized action.

## Execution status

The user approved this exact acceptance tag/prerelease proposal. The annotated
`acceptance-20261004` tag was pushed at the B commit listed below. GitHub draft
release ID `403066673` was created with `prerelease=true`, title/body reviewed,
and Latest unselected. After all assets were uploaded and checked, it was
[published](https://github.com/yomingpan/clipai/releases/tag/acceptance-20261004).
GitHub API confirms `draft=false`, `prerelease=true`, and exactly 20 uploaded
assets. The page shows 22 assets because GitHub adds two source archives.

All 19 files listed in the local SHA256 manifest were verified immediately
before upload. Browser upload initially required the Edge ChatGPT extension's
Allow access to file URLs permission. The user enabled it; no extension/security
setting was changed automatically. All 20 remote names, sizes and GitHub SHA256
digests were compared with actual local bytes before publishing. Anonymous
download verification passed for all 20 assets; the downloaded B passed actual
signature/manifest/inventory admission. The follow-up evidence records the
credential-free requests, full hashes and bounded Range recovery. Actual About
remains pending. Stable latest remains `v3.7.8`.
Publication metadata: `artifacts/github-acceptance-publication-20261004.json`.
Manual update steps: [About acceptance guide](../testing/github-acceptance-about-20261004.md).

## Exact proposed release

- Repository: `yomingpan/clipai`; existing stable `v3.7.8` must remain untouched.
- New tag: `acceptance-20261004`, target B source
  `7bcccb1ea792a8e725d174872f43de5defcc87b4`.
- Title: `ClipAI installer/update acceptance — 3.7.8 to 3.7.9`.
- First prepare as draft, upload and inspect the complete assets; publication,
  if directly authorized, sets `prerelease=true` and `make_latest=false`.
- Setup A hash `961704178b9a10a160cf27fa0562695a5602eee036bc30319183feec2d4da391`.
- Setup B hash `3b4ea9c2be8dce0e6e03485a0d409e5ff2c3265b41c5d45a4016cdde427813c3`.
- B managed bundle hash `47f08a74912c5130a41c50dff22e3a5b298070856ee37078b30b7a83b6f7d2eb`.
- These technical candidates are unsigned and use a shared local pair authority.
  They cannot authorize updates to an earlier fix or an official installation.

Upload-ready folder: `artifacts/github-acceptance-20261004/`. It contains both
Setups/bundles, the common public keyring, the test catalog, notices/proofs and
SHA256SUMS.txt. `catalog.json` is copied from B and changes only its bundle URL to
`https://github.com/yomingpan/clipai/releases/download/acceptance-20261004/clipai-managed-3.7.9.zip`.
This catalog's fields and B bytes are validated locally. That URL is now served
by the explicitly authorized prerelease. Formal asset catalogs
and production `latest` are unchanged.

## After publication

Check the release is prerelease/non-latest and the existing latest tag is still
`v3.7.8`. Download the assets anonymously over HTTPS, verify SHA256SUMS and compare
the served B catalog identity with its bundle. Only then install the paired A
in an authorized disposable scope or manually retain/remove/reinstall Candidate.
Automated checks must not remove an existing user installation or rewrite keys.

Use A's installed Python with `-I` and `launch_isolated_about.py`, the existing
Candidate roots, and the explicit acceptance catalog URL. Click About Update;
record the actual B result, matching version/health/payload, retained synthetic
state, reboot and failure recovery. The same B bundle is already extracted and
hash-proven inside Setup B. No new channel or verification bypass is introduced.

Windows publisher signing, native/license admission and first-user observations
are still independent gates. Publishing an experimental prerelease does not
pass them or permit a stable release. The original prompt prohibits pushing
tags/public formal releases without direct authorization; this document is the
concrete reviewable proposal for any needed acceptance tag/public test release.

References: [GitHub release API](https://docs.github.com/en/rest/releases/releases)
(`draft`, `prerelease`, `make_latest`) and
[direct asset links](https://docs.github.com/en/repositories/releasing-projects-on-github/linking-to-releases).
