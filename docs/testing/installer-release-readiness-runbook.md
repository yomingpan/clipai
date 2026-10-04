# Installer / About release acceptance runbook

Date: 2026-10-04. Owner: release maintainer. Scope: Windows 11 x64, standard user.
Local evidence is in [the matrix](../evidence/installer-release-readiness-20261004.md).

## Reproduce the local technical candidate

These commands consume the existing r4 signed bundle; no wheel/dependency rebuild,
no generated signing key, no tag creation and no GitHub publication. Run at the
repository root with the known Python 3.12 developer environment. Pick a **new**
output directory for every build; existing output is deliberately rejected.
The source commit is the app's input identity; packaging changes remain a working
tree diff recorded separately in provenance. The `v3.7.8` value is an intended
catalog identity only, not evidence of a new verified Git tag or newer release.

```powershell
.venv/Scripts/python.exe -m scripts.build_setup_release `
  --bundle artifacts/first-install-preview/preview-383019e21d70403ba2261efb99cf427a/stage/bundle.zip `
  --catalog artifacts/installer-release-readiness/r4-publication/catalog.json `
  --keyring artifacts/first-install-preview/preview-383019e21d70403ba2261efb99cf427a/stage/setup-engine/managed-update-trusted-keys.json `
  --inputs packaging/windows/setup-inputs.json `
  --runtime-archive artifacts/first-install-candidates/runtime-readable/download.archive `
  --verifier-archive artifacts/first-install-candidates/verifier-readable/download.archive `
  --compiler artifacts/first-install-build/tools/inno-6.7.3/ISCC.exe `
  --output-root artifacts/installer-release-readiness/<new-build-id> `
  --tag v3.7.8 --source-commit a0502d34cfa2b1ab554c480d39b8b8813d1ef201 --technical-candidate

.venv/Scripts/python.exe -m scripts.verify_packaged_app --stage <build>/stage --output <build>/output/packaged-smoke.json
.venv/Scripts/python.exe -m scripts.verify_setup_extraction --assets <build>/output
.venv/Scripts/python.exe -m scripts.verify_release_assets --assets <build>/output
```

`r4-publication/catalog.json` was locally generated from r4's recorded bundle
size/hash/manifest/key, with the fixed immutable tag URL; that URL has **not** been
published by this task. For a future release use `build_managed_release`'s actual
catalog/keyring and bundle instead. Never point production latest at this fixture.

```powershell
.venv/Scripts/python.exe -m experiments.first_install.accept_preview `
  --product "ClipAI Candidate" --version 3.7.8 `
  --setup <build>/output/ClipAI-Candidate-Setup-3.7.8-windows-x64.exe `
  --output artifacts/installer-release-readiness/<new-acceptance-id>
```

This bounded native harness refuses any existing Candidate program/shared root
or registry entry. It creates only its own test child/sentinel, never terminates
a user's app, and retains shared transaction evidence. Desktop runtime startup
may skip when a user's ClipAI is active: record that as pending, not passed.
It is a developer-host Setup test, not clean VM, NIC isolation or About evidence.

## Prepare actual device acceptance

1. Supply an existing authorized VM and licensed Windows image; do not enable
   a hypervisor or change host defenses as an implicit test setup. Record Windows
   edition/build, standard-user rights, CPU, architecture, prerequisite versions
   and snapshot identity. No Python/Git/OpenSSH/checkout on the VM. Take the clean
   snapshot before any candidate install. Limit to two normal cycles plus one
   reset per failure; 10-minute install and 2-minute launch/settlement ceilings.
2. Fix candidate A/B and record tag/commit, every asset hash and public keyring.
   B must have a real newer wheel/project/manifest version (for example a reviewed
   3.7.9 after A=3.7.8); rebuilding r4 with the same version is not B. Use reviewed
   final native/runtime/license inputs; keep security decisions separate from app
   version. Copy Setup/assets to a VM-owned directory and record bytes again.
3. Use isolated HTTPS distribution with the immutable B bundle and catalog.
   The existing `ManagedUpdateRuntimeConfiguration.catalog_url` composition
   parameter is the injection seam. Ordinary CLI currently uses production
   latest: an isolated VM test launcher must compose that existing configuration
   and the same runtime/container, without patching production latest, adding a
   channel, monkeypatching verification or bypassing About's typed intent. Use `experiments/first_install/launch_isolated_about.py` with the installed
   Candidate version venv's Python, `-I`, explicit install/shared roots and
   `--catalog-url https://<isolated-host>/catalog.json`. It proves installation
   ownership/running identity, retains the installation keyring, composes the
   real runtime and waits for the operator's About click (5-minute default,
   10-minute maximum). It refuses production GitHub URLs/credentials, emits
   real launch health and uses typed shutdown on timeout. No automatic update.
   Helper source/URL tests pass; actual attended launch and About B remain
   pending until a VM and comparable trusted A/B are supplied. The loopback
   transaction fixture does not prove an About click.
4. Disconnect the VM NIC; install A. Observe immediate real phase/terminal
   feedback, Start Menu/desktop/icon and final Launch. Exit Setup, clear only
   test-owned extraction temp, reboot, and launch again. Record installed-wheel
   import paths, current version and launcher health. Then reconnect; only with
   fresh explicit authorization use provider credentials and trigger first Action.
5. Click About Update through the injected source. Observe checking → restart
   only after matching readiness; prove B current payload identity, A retained,
   shared synthetic config/state retention and B healthy after reboot. Exit via
   Tray, uninstall through Windows/Setup, check owned shortcuts/registration
   removed, synthetic data retained; reinstall and compare bytes. Leave users'
   credentials/installs out of all automated scopes.
6. Sample disk usage during extraction, environment preparation and settlement;
   record peak/final allocated/logical bytes separately, Setup size and phase
   timings. Measure before choosing limits; neither download size nor one final
   directory total proves peak disk usage.

## Failure/device matrix and release gate envelope

Reset to the clean snapshot or proven A snapshot for each case. Keep the signed
valid A and its exact keyring; inject faults at transport/adapter seams, never by
turning off signature checks. Every case records command/action, candidate hash,
Windows/snapshot, outcome/error code, active version, user-data comparison,
limitations and next step. Use passed/failed/pending/blocked.

| Case | Required safe end state | Evidence level required |
| --- | --- | --- |
| Normal A → About B → reboot → remove/reinstall | B healthy; retained data equal except documented app writes | clean VM / actual UI |
| Download interrupted | A usable; no new current pointer | deterministic + device transport |
| Bundle hash/manifest/signature changed | rejected before preparation/commit; A usable | real signature + device |
| Preparation failure | A usable; owned candidate cleanup settled | fault seam + device |
| B startup failure | matching health rejected; A health proven after rollback | fault seam + device |
| Active app / simultaneous update/remove | one admitted owner; no user process termination | native multi-process |
| Different logon session / same canonical root | same Global gate excludes second writer | real cross-logon |
| Chinese / space path | install/selfcheck/maintenance succeed | native path probe |
| Setup/browser Windows trust | exact signed hash; defenses unchanged; prompts recorded | final downloaded file |
| New user first result | explicit Action; actual result; assistance counts/blocks | observation |

Acceptance JSON for the final signed candidate uses:

```json
{
  "setup_sha256": "<final signed Setup hash>",
  "bundle_sha256": "<the one signed managed bundle hash>",
  "gates": {
    "clean_vm_cycle": "pending",
    "failure_recovery": "pending",
    "reboot": "pending",
    "cross_logon_gate": "pending",
    "native_admission": "pending",
    "browser_windows_trust": "pending",
    "first_user_result": "pending"
  }
}
```

Each passed label must link to the exact-hash evidence matrix, including native
component/license coverage and any expected app writes. `verify_release_assets
--require-release-ready --acceptance ... --publisher ...` additionally verifies
actual final Setup publisher/timestamp. It does not perform or certify those
human/device observations. Signing or repackaging invalidates old hashes and
requires resealed provenance plus affected proofs; same bundle must stay exact.
No VM/signer means these gates stay blocked/pending and public release is NO-GO.
Publication requires separate direct authorization; see the release checklist.
