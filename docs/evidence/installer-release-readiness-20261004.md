# Installer release readiness evidence

Date: 2026-10-04 (Asia/Taipei). Decision: **NO-GO for public release**.
Baseline HEAD is `a0502d34cfa2b1ab554c480d39b8b8813d1ef201`; packaging/CI
changes are an uncommitted working-tree diff. No tag push, release publication,
hypervisor/security change, credential transmission or purchase occurred.
Original `.tmp/` and user documents/installations/data were preserved.

Follow-up: the changes recorded below were subsequently committed as `64b61c9`.
The user reports all seven manual candidate steps passed, including reboot and
first Action. This does not establish clean-VM, signed-publisher or About A→B
evidence. A reported first-save yellow tray and the requested opt-in full
removal are handled in [follow-up evidence](tray-readiness-full-removal-20261004.md);
the exact original asset identities below remain historical.

## Exact technical candidate

- App: 3.7.8; source content verified against baseline Git commit. `v3.7.8`
  is a requested catalog identity, **not a newly verified/pushed tag**.
- Build: `artifacts/installer-release-readiness/delivery-20261004/`.
- Setup: `output/ClipAI-Candidate-Setup-3.7.8-windows-x64.exe`, 34,941,131 bytes;
  SHA-256 `0f3789af3c44842c0759d2bdd8f2434c2ea68d88e29924471148befbe5cb6e3c`.
- Same bundle: `output/clipai-managed-3.7.8.zip`, 20,651,806 bytes;
  SHA-256 `5a01500508eb35575d72351d1d5c7618383197964f8b4b564ba97be1c27b2223`.
- Manifest trust: original r4 local authority, actually verified by the existing
  production stager; no test-key bypass and no newly generated key. It is not
  the official publisher authority. Private r4 signing key remains removed.
- Windows trust: **unsigned Setup**. Component distribution admission pending.
  Native Candidate cycle uses independent `ClipAI Candidate` directories,
  Start Menu/Desktop identity and `ClipAI.LocalAcceptance.Candidate` registration.
- `output/` contains catalog, public keyring, notices, per-wheel/lock/staged-file
  provenance, packaged/extraction proofs, local acceptance, test summary,
  intentional publication rejection and `SHA256.txt`. Earlier build directories
  are exploratory candidates, not the final delivery hash.

## Evidence matrix

| Gate / check | State | Command / result | Environment and limits |
| --- | --- | --- | --- |
| Baseline | passed | `git status --short`, `git log -1 --format="%H %s"`; baseline unchanged | two user planning files initially untracked; unrelated temp contents inaccessible in some scopes, preserved |
| Ownership diagnosis | passed | [diagnosis](installer-release-ownership-20261004.md) | Yellow/local packaging seam; one install/update engine retained |
| VM/signer/runner inventory | blocked / pending | [exact commands and sources](../specs/installer-release-inputs.md) | Windows 10.0.26200.0, Python 3.12.14 x64; WMI denied; no confirmed clean VM/image/license/signer/CI access |
| Bundle→Setup assembly | passed | `python -m scripts.build_setup_release … --technical-candidate`; [full command](../testing/installer-release-readiness-runbook.md) | exact r4 bundle consumed; no app rebuild/dependency resolution/key generation; tag not verified |
| Source correspondence | passed | same build CLI compared complete first-party wheel and signed payload with `git archive a0502d34…` | text newline normalization only; HTML's CRLF/LF difference confirmed; binary resources exact |
| Substitution / boundaries | passed | `.venv/Scripts/python.exe scripts/run_unit_tests.py -- tests/platform/test_setup_release_builder.py tests/scripts/test_build_setup_release.py tests/scripts/test_managed_release_workflow.py tests/architecture -q`; 83 passed | unit/fault/AST, not device proof; catalog/bundle/manifest/keyring/pins/evidence substitutions rejected |
| Complete unit suite | passed | `.venv/Scripts/python.exe scripts/run_unit_tests.py -- -q`; **1,909 passed, 46 deselected**, 55.94 s | latest code and helper policy tests; separate from historical 1,878 result |
| Existing managed transaction/transport | passed | `.venv/Scripts/python.exe scripts/run_unit_tests.py -- tests/e2e/test_managed_update_bundle.py tests/e2e/test_managed_update_loopback_http.py -m integration -q`; 4 passed, 143.92 s | real subprocess/offline preparation/Ed25519/loopback + fixture app/health/fault matrix; not full app/About/VM |
| Installed-wheel import identity | passed | `python -m scripts.verify_packaged_app --stage <delivery>/stage --output <delivery>/output/packaged-smoke.json` | same admitted 41 wheels and hashed lock through existing materializer; no-index; poisoned parent Python config; imports below `.venv/Lib/site-packages`, not checkout; NIC not disconnected |
| Compiled EXE payload bytes | passed | `python -m scripts.verify_setup_extraction --assets <delivery>/output` | native Setup extracts and hashes bundle/public keyring; matching bundle SHA receipt; no installation/removal in this mode |
| Candidate asset consistency | passed | `python -m scripts.verify_release_assets --assets <delivery>/output` | Setup, ZIP/catalog/keyring/version/URL/manifest/lock/wheels/notices/evidence match; URL not actually published |
| Public promotion refusal | passed rejection / blocked publication | same `verify(..., require_release_ready=True)` rejects technical candidate; `publication-rejection.json` | no GitHub write or signer use; this proves rejection, not public readiness |
| Local compiled Setup cycle | passed | `python -m experiments.first_install.accept_preview --product "ClipAI Candidate" --version 3.7.8 --setup <delivery>/output/ClipAI-Candidate-Setup-3.7.8-windows-x64.exe --output artifacts/installer-release-readiness/native-cycle-20261004` | actual developer-host standard-user EXE; owned Candidate scope, empty PATH; no clean VM/NIC isolation/reboot |
| Desktop runtime / first Action | pending | native harness twice detected user's running ClipAI and skipped desktop startup | did not stop user's app or reuse provider-key authorization; import/Tk/clr success does not prove first result |
| Preview terminal captions | passed | `python -m experiments.first_install.setup_result_probe --script experiments/first_install/preview_setup.iss --stage <r4>/stage --compiler <pinned-ISCC>` | shared wizard compiled with harmless fixture; final failure/success captions true, exits 100/0; proof `artifacts/first-install-diagnostic/setup-result-4994e9984f3342a7b749ec7ba5428a39/proof.json` |
| Isolated About launcher | passed source/policy / pending device | `… scripts/run_unit_tests.py -- tests/scripts/test_isolated_about_launcher.py -q`; 6 passed | real runtime/config/keyring/identity seam implemented; attended launch and actual newer B not yet exercised |
| CI | passed local source tests / pending remote | shared builder/extraction/packaged/asset gates, immutable Actions, repository contents read, candidate upload only | no workflow push/run; no automatic draft creation or publish; compiler tool install only configured for runner |
| Final native/license/publisher | blocked | [inputs/admission](../specs/installer-release-inputs.md) | OpenSSH Preview; historical runtime unsigned native inventory; final signer unavailable; notices are not a complete license certification |
| Clean VM / reboot / About A→B | blocked | [bounded device runbook](../testing/installer-release-readiness-runbook.md) prepared | no VM/snapshot/image/license confirmed; B must actually exceed A version; r4 rebuild not used as B |
| Cross-logon contention / NIC offline / peak disk | pending | runbook matrix prepared | previous/native process evidence does not replace real cross-logon, NIC disconnection or sampled peak disk |
| Browser trust / new users | blocked / pending | final-hash acceptance envelope and release checklist prepared | no final signed download or new-user observations; no defenses disabled |

## Actual native cycle results

| Operation | Result | Time |
| --- | --- | --- |
| Initial install | exit 0; signed identity, full `main`/Tk/clr loading and native registration/shortcuts confirmed | 94.77 s |
| Duplicate install | exit 100; original marker bytes unchanged | 12.11 s |
| Removal with owned active child | exit 100; marker unchanged; only the test's child was stopped afterward | 13.70 s |
| Broken app venv removal | exit 0 using same Setup after renaming only test-owned version Python | 24.17 s |
| Retained-data reinstall | exit 0; synthetic sentinel bytes equal; identity/import/native integration confirmed again | 93.30 s |
| Final removal | exit 0; owned program root/native registration removed; synthetic sentinel then deleted, shared transaction evidence retained | 19.12 s |

Program logical bytes were 253,279,088 initially and 253,279,202 after reinstall.
These are directory totals, not allocated/peak disk usage or an installation SLA.
Setup hash is unchanged throughout. No user credentials/installation were used.
Two desktop startup skips are explicitly **pending**, not success.

## Remaining decisions and next actions

1. Supply an authorized resettable Windows 11 x64 VM, licensed image and standard
   user; execute the attended runbook, including actual About B and reboot. A/B
   need a common approved trust authority; r4's deleted private authority cannot
   sign B, and its keyring is not silently replaced with official keys.
2. Release owner admits runtime/native/dependency notices, selects a supported
   verifier and resolves compiler commercial eligibility. Confirm lawful signer,
   publisher subject, CI signing configuration and final native file coverage.
3. Build a genuinely newer comparable release at a reviewed commit/tag, keep one
   bundle for both paths, sign final files, reseal hashes and rerun affected gates.
4. Observe final browser/Windows trust and a few novice first results. Public
   promotion requires direct authorization and the strict final-asset gate.

No public-readiness claim is made. The prompt's independent local implementation,
candidate delivery, tests, runbook and evidence work is complete; device/signing
gates remain explicitly open. See [updated plan](../specs/installer-release-readiness-plan.md)
and [release checklist](../RELEASE_CHECKLIST.md).
