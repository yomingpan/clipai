# 3.7.18 release preparation evidence

Date: 2026-10-06. Status: **not published**. The maintainer authorized autonomous
3.7.18 release work and explicitly selected unsigned Windows Setup with no paid
certificate/service. Official managed Ed25519 content signatures remain required.

## Source and compatibility

- Preparation commit: `a34776776774b876c98fe712de31e929573acfda`.
- `pyproject.toml` is 3.7.18. The catalog requires launcher 3.7.18 because older
  stable hosts cannot acquire the corrected preparation/health deadlines through
  an app-only update. Older installs need validated Setup maintenance or retained
  data reinstall. Candidate settings/API keys are not automatically transferred.
- Only `release-validation/3.7.18` was pushed. No `v3.7.18` tag or public Release
  was created. Official signing secret/key ID/public keyring existence was checked
  without reading secret values; actual official authority self-verification is pending.

## Completed checks

- Local full unit suite before policy change: 1,989 passed, 64 deselected.
- Local full unit suite with explicit unsigned policy: 1,996 passed, 64 deselected,
  74.00 seconds; includes architecture tests.
- Separate architecture run: 56 passed. Language pack validation: 2 passed.
- Real managed update integrations: 4 passed, 213.46 seconds. They cover loopback
  HTTP transactions, actual bundle/signature/offline setup and recovery cases.
  Native execution was required: sandboxed child OpenSSH/filesystem operations
  failed; sandbox failure is not recorded as a product pass.
- [Windows source/unit/architecture CI](https://github.com/yomingpan/clipai/actions/runs/37463625186):
  Python 3.10, 3.11, 3.12 and 3.13 all succeeded at preparation commit.
- [Candidate build CI](https://github.com/yomingpan/clipai/actions/runs/37463625043):
  lock/wheelhouse sealing, signed managed bundle, complete transaction gate,
  fixed-input Setup, installed-wheel smoke, compiled extraction and asset checks
  all succeeded. This branch uses a disposable authority and technical identity;
  it cannot be promoted into an official release.

## Exact downloaded technical artifact

- GitHub artifact ID: `11413388151`; ZIP 56,216,426 bytes; SHA-256
  `ab8458468c724ceb63c9a5474f011a307295adb9dc7b3987d09bff0f46b765c1`.
  Download hash equals GitHub's artifact digest.
- Setup: `ClipAI-Candidate-Setup-3.7.18-windows-x64.exe`, 34,954,907 bytes; SHA-256
  `b9a644a34a81bcc1e5e1dc781686bc6c6211f571c4d6e4a7d0ab98bf3c799c8a`.
- Bundle: 20,660,280 bytes; SHA-256
  `6e06ee8847461854133779a122bd8dae3ff402d5b818a127f0c11187e6f74de7`.
- Native signature inspection of the actual EXE returned `NotSigned`, null
  publisher and null timestamp. The checker initially inherited PowerShell 7's
  module path into Windows PowerShell 5.1 and could not load the security module.
  It now uses the child's built-in module path and terminating errors; the real
  inspection was rerun successfully. No installer was launched by this check.

## Unsigned policy and remaining work

`verify_release_assets --require-release-ready --publisher-policy unsigned`
requires the same policy in exact-hash acceptance and actual `NotSigned` status.
It rejects damaged/untrusted/unknown/unexpected valid signatures and still rejects
technical identity, unadmitted inputs, substitutions and missing device gates.
Default signed policy still requires a matching publisher/timestamp. This policy
is documented in the contracts, checklist, runbook and proposed release notes.

Remaining: supported verifier selection (current Win32-OpenSSH input is upstream
Preview/non-production), component/license/native admission, official-mode CI and
official authority self-verification, exact final device/clean VM/reboot/cross-logon/
browser/first-use evidence, validated upgrade/retained-data maintenance, immutable
tag/assets/publication and post-publication verification. The prior r3 success
and technical CI do not satisfy these remaining gates.
