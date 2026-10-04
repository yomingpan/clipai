# Installer/update acceptance follow-up — 2026-10-04

This supplements the original readiness matrix. The user reported the tray and
full-removal candidate passed manual testing, asked to continue the four next
steps, deferred clean Windows 11 VM testing because no VM/second device exists,
and selected GitHub as the proposed download location. Stable publication is
still NO-GO. The acceptance tag/draft follow-up is recorded below.

## Tested source and validation boundary

Source changes are committed through
`cb7812387b4062813b0a1aacabd9ff09be0153a3`. Source validation was pushed to the
new remote branch `release-validation/installer-20261004`; the subsequently
authorized acceptance tag is recorded below. Remote `develop`, `main`,
existing published tags/assets and production `latest` were not changed.

- `7bcccb1`: real app version 3.7.9; branch-triggered shared candidate CI.
- `e1718da`: actual paired A/B preparation and corrected tag/authority tests.
- `3e262a0`: seal resolved wheelhouse hashes for real offline pip installs.
- `cb78123`: restrict GitHub About acceptance URLs to a separate acceptance tag.

Branch CI has read-only contents permission and uploads artifacts only. Its
temporary `local-validation-*` authority cannot pass official packaging. Tag
secrets are excluded from branch steps. The final cleanup removes temporary
private/public key files and the generated keyring.

## Verification performed

Local Windows checkout, `.venv/Scripts/python.exe`:

- `python scripts/run_unit_tests.py`: **1,949 passed, 48 deselected**, 61.69 s;
  log `artifacts/acceptance-final-unit-20261004.log`.
- Targeted release/architecture checks: **89 passed**, 9.09 s.
- Targeted GitHub URL/pair/architecture checks: **73 passed**, 5.73 s.
- Targeted compileall passed.

Remote [Windows CI 37209482588](https://github.com/yomingpan/clipai/actions/runs/37209482588)
at `cb78123`: supported constrained Python 3.10/3.11/3.12/3.13 jobs all passed.
Python 3.10 job `111457553743` records 1,949 unit passes and the separately
executed **56 architecture tests**. The scheduled unpinned job was correctly
skipped for this push.

Remote [candidate build 37209482511](https://github.com/yomingpan/clipai/actions/runs/37209482511)
at `cb78123`: **passed**, including the complete transaction, packaged-import,
extraction, asset validation, artifact upload and signing-material cleanup steps.
Job `111457553901` records 1,949 unit passes (50.00 s), synthetic lifecycle
1 pass, loopback HTTP 2 passes (1.66 s), and real bundle transaction/fault matrix
2 passes (77.85 s). This does not stand in for a clean VM or human About click.

CI candidate identities (distinct from the local shared-authority A/B pair):

- Setup SHA256 `37750eeb4fab0014b92f36da36ea556e7684372f06903519b52c6519e1e47a58`.
- Bundle SHA256 `de7474f8a58000b40668604146e9434d24d2335be12b478fce9f46eb4505ca83`.
- Asset validation reports `status=passed`, `release_ready=false`.
- [Artifact 11306285960](https://github.com/yomingpan/clipai/actions/runs/37209482511/artifacts/11306285960),
  `clipai-v3.7.9-37209482511`, 56,197,302 bytes; ZIP SHA256
  `5ad86fca374d1de965794a7c7339271205628bcee76fc7bd77967ea3c16fe13d`.
  These hashes come from the completed job log and GitHub artifact metadata;
  this record does not claim a second local download/revalidation of the ZIP.

Earlier candidate CI found a real offline hash mismatch after compiling Setup.
The source lock admitted an sdist while the final offline wheelhouse contained a
locally built wheel with a different hash. A minimal native pip invocation
failed with the old lock and passed with the actual wheel hash. The fix preserves
source-hash checks before building and seals final runtime hashes afterward,
without another dependency resolution. See
[diagnosis and evidence](offline-wheel-lock-diagnosis-20261004.md).

## Actual paired local candidates

`artifacts/installer-acceptance-pair-20261004/pair.json` and
`final-validation.json` record:

| Candidate | Version/source | Setup SHA256 | Bundle SHA256 |
| --- | --- | --- | --- |
| A | 3.7.8 / `85c5984878acee69921b8843ade10380c640916d` | `961704178b9a10a160cf27fa0562695a5602eee036bc30319183feec2d4da391` | `4f57136a5107cd2933c808e6ea20e99334a71bfbc17425edd9c1c742be485b83` |
| B | 3.7.9 / `7bcccb1ea792a8e725d174872f43de5defcc87b4` | `3b4ea9c2be8dce0e6e03485a0d409e5ff2c3265b41c5d45a4016cdde427813c3` | `47f08a74912c5130a41c50dff22e3a5b298070856ee37078b30b7a83b6f7d2eb` |

Both passed actual signed bundle admission, compiled Setup generation, installed
wheel imports, compiled extraction equality and asset validation. A's app wheel
is the already-admitted wheel; B's wheel is built once from its real Git source.
The same B bundle is inside Setup B and named by the test About catalog.

Shared public keyring SHA256:
`7faad3d8f31120882e4fe7c6aa5f020f47e7e0410fb70b6fbc0ca223b34aa7cd`.
Both keyrings were compared byte-for-byte. Pair private key removal was verified.
This authority is distinct from older local candidates and the official release.
The user's existing installation, keyring, config and API keys were not modified.
No actual A/B installation or attended About update is claimed here.

The pair was built with `python -m experiments.first_install.prepare_acceptance_pair`,
using original A assets in `artifacts/installer-removal-fix-20261004/delivery-final2/output`,
B source `7bcccb1`, the bundled build Python, fixed runtime/verifier archives,
Inno 6.7.3 and `packaging/windows/setup-inputs.json`. Complete invocation and
manual follow-up are in the [runbook](../testing/installer-release-readiness-runbook.md).
Build log: `artifacts/acceptance-pair-build-20261004.log`.

## GitHub handoff and remaining gates

`artifacts/github-acceptance-20261004/` contains 20 upload-ready files. Its SHA256
manifest was checked against every other file. The copied B test catalog changes
only the download URL to the proposed `acceptance-20261004` release; bundle hash,
size/version identity are checked against actual B bytes. The user approved
creating and publishing this experimental prerelease. The annotated tag was
pushed at B source `7bcccb1`; tag object
`87a7c17fdb436536c8d2339462c9ab94c2f51b62` was checked through the GitHub API to
resolve to that exact source commit. Draft release `403066673` was prepared.
After the user enabled Edge's required file-URL permission, all 20 assets were
uploaded. Before publication, every remote name, size, uploaded state and GitHub
SHA256 digest was compared against the actual local file bytes.

The [acceptance release](https://github.com/yomingpan/clipai/releases/tag/acceptance-20261004)
is now public: API confirms `draft=false`, `prerelease=true`, 20 uploaded assets.
The page counts 22 including GitHub's two generated source archives. The stable
latest endpoint still returns release ID `389999189`, tag `v3.7.8`, with its
original five assets. No extension/security setting was changed automatically.
Publication metadata is in `artifacts/github-acceptance-publication-20261004.json`;
page proof is `artifacts/github-acceptance-published-20261004.jpg`.
Anonymous download/admission verification: **passed**. Command:
`.venv/Scripts/python.exe artifacts/verify-github-acceptance-20261004.py`.
The verifier used credential-free public HTTPS requests, downloaded all 20
assets and compared every complete file SHA256 against the prepublication local
bytes. Large full-stream requests stalled on this host; supported HTTPS Range
requests retrieved the four large files in 108 bounded chunks. Each assembled
file was checked with its original full SHA256; no partial file was accepted.
TLS verification remained enabled and no token/browser cookie was used.

The served catalog parses as 3.7.9, with the exact public B URL, size/hash and
manifest identity. The real `VerifiedManagedBundleStager` then admitted the
downloaded B using the already-hash-pinned shared pair keyring and the actual
Ed25519 verifier, including manifest and payload inventory verification.
Full report:
`artifacts/github-acceptance-download-20261004-verified/download-verification.json`.
Report states `anonymous_https=passed`, `bundle_signature_admission=passed`,
`actual_about_update=pending`, `clean_vm=deferred_by_user`. This evidence does
not assert an attended About click, installation, restart or Windows trust gate.

The [manual About guide](../testing/github-acceptance-about-20261004.md) gives the
operator the exact paired A, installed interpreter and acceptance catalog URL.
Release assets and post-publication checks are in
[GitHub acceptance proposal](../specs/github-acceptance-release.md).

| Requested next step | Current result | Remaining evidence |
| --- | --- | --- |
| Clean Windows 11 | deferred by user | New device/VM, offline/reboot/cross-logon/space measurements |
| Actual About A → B | pair/prerelease, anonymous asset hashes and B signature admission passed | Paired A install, actual About click/health/retained data |
| Remote CI and signing | Supported Windows source CI and complete candidate CI passed | Windows publisher signer, timestamp/final hashes, official native/license admission |
| Final user distribution | Complete experimental prerelease published | Final signed candidate, browser Windows trust, first result observations |

The official release-ready gate correctly rejects these technical/unadmitted
assets. Experimental hosting does not pass that gate. No paid signing service,
hypervisor, OS trust changes, formal key rotation, or stable publication occurred.
