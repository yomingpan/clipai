# Tray readiness and explicit full removal

Date: 2026-10-04, Asia/Taipei. Local technical candidate, not public release.

Follow-up: committed as `01bfb04`. After that commit the user reports the new
fix candidate passed manual testing with no issues. This closes the reported
local manual follow-up, while clean VM and actual About A→B remain independent.
The user subsequently deferred VM/second-PC testing because neither is available.

The user reports all seven manual installation/startup/reboot/removal/reinstall
steps passed on the earlier `delivery-20261004` candidate. This is user-reported
developer-device evidence, not clean-VM, signed-publisher or About A→B acceptance.
The same report identifies a yellow tray after the first provider was saved.

## Changes and regression evidence

- Real typed runtime save with the actual configuration and lifecycle
  coordinators reproduced `succeeded` settings plus `warning` tray. Command:
  `.venv/Scripts/python.exe scripts/run_unit_tests.py -- tests/app/test_runtime_provider_readiness.py -q`.
  Red: `AssertionError: 'warning' != 'idle'`. Configuration projection now
  supplies active-binding readiness through `OperationTracker.set_ready`;
  lifecycle remains the only owner of tray status. Pending save remains yellow;
  successful save returns blue without restart. Processing/success/error are
  protected from an unrelated readiness projection.
- Generalized `UninstallIntent` / `UninstallCoordinator` / `FilesystemUninstaller`
  carry explicit `delete_user_data=False` by default. Both Setup and Windows
  uninstall choose keep-data or full removal; full interactive removal requires
  confirmation. Cancel does not dispatch. Install cannot request deletion.
- Full removal deletes only proven dedicated program/shared roots and native
  receipts, including shared configuration/API keys, logs, history and caches.
  Native validation settles before shared deletion. Unknown program files,
  redirected paths and another installation's transaction records fail closed.
  Data-cleanup failure preserves owner proof for same-Setup retry. Partial data
  deletion cannot be rolled back. [Ownership diagnosis](full-removal-ownership-20261004.md).
- One bounded Windows supervisor waits for its actual helper process, cleans
  only its generated directory, then reports result. It does not sweep previous
  temp folders, delete exported files/prerequisites, alter OS history or stop a
  user process. UTF-8 JSON handles Chinese/space/apostrophe helper paths.

| Verification | Result | Scope |
| --- | --- | --- |
| Complete unit suite | 1,930 passed, 48 deselected; 113.97 s | `.venv/Scripts/python.exe scripts/run_unit_tests.py -- -q`; includes architecture; final UTF-8 literal separately exercised below |
| Focused policy/architecture | 79 passed, 2 deselected | new readiness/removal/entry tests plus architecture |
| Native helper exit/cleanup | 2 passed, 2 deselected; 4.53 s | `… run_unit_tests.py -- tests/platform/test_maintenance_helper.py -m integration -q`; actual Windows process/wait/filesystem, fixture worker; Chinese/space/apostrophe root; terminal message box suppressed only |
| Compiled full-removal projection | passed, exit 100/0 | `python -m experiments.first_install.setup_result_probe --script packaging/windows/setup.iss --stage artifacts/installer-release-readiness/delivery-20261004/stage --compiler artifacts/first-install-build/tools/inno-6.7.3/ISCC.exe --delete-user-data`; harmless fixture engine proves explicit flag/failed and successful captions, no app removal |

Compiled projection proof:
`artifacts/first-install-diagnostic/setup-result-ba3cfce66cf4408b89d20dc540e7cd97/proof.json`.
An initial probe caught silent full removal being blocked by an interactive
confirmation (120 s timeout). `WizardSilent` now avoids that dialog only for
explicit automation flags; interactive full removal still defaults to No.

## Candidate identity and remaining acceptance

The changed app wheel is rebuilt once offline with bundled setuptools 84.0.0
and wheel 0.48.0; existing dependency wheel bytes are reused. A fresh ephemeral
local acceptance manifest authority is required because the old r4 private key
was deleted. Its private key is removed after building. This is neither the
official publisher authority nor an About update to the existing installation.
The formal Setup builder consumes that one signed bundle and bootstraps from
its admitted wheel. Git source content binds to local snapshot
`85c5984878acee69921b8843ade10380c640916d` without changing HEAD or creating a tag.
Version remains 3.7.8; `v3.7.8` is an intended catalog identity, not a verified tag.

Final delivery asset identities and packaged/extraction/asset proofs are in
`artifacts/installer-removal-fix-20261004/delivery-final2/output/`. Installed-wheel
imports, actual compiled payload extraction and asset consistency all passed
against this exact candidate. Commands: `python -m scripts.verify_packaged_app
--stage <delivery>/stage --output <delivery>/output/packaged-smoke.json`,
`python -m scripts.verify_setup_extraction --assets <delivery>/output`, and
`python -m scripts.verify_release_assets --assets <delivery>/output`.

- Setup: `ClipAI-Candidate-Setup-3.7.8-windows-x64.exe`, 34,952,779 bytes;
  SHA-256 `5f99aa2f6118392b2a7aa24a1346989f43497a1a226fe59fc59bac84c0965fb3`.
- Same bundle: 20,658,732 bytes;
  SHA-256 `a0a8f90149e43297fe78205bf65de09212f6c2b75ff3d56df859f227112a64ec`.
- Frozen wizard/packaging adapter hashes match current source. Final build's
  ephemeral private key removal confirmed. Default Setup logging is off;
  explicit `/LOG` is caller-owned diagnostic output. Candidate remains unsigned.
- Final focused entry/packaging/readiness tests: 36 passed, 15.05 s.

Earlier directories
under `installer-removal-fix-20261004` are exploratory builds.

No user installation, key or settings were modified automatically. New native
full-app removal and Windows uninstall dialog/device acceptance remain for the
operator; fixtures do not substitute for those observations. No clean VM,
publisher signature, remote CI or actual newer About release was added.

Retest with the final new Setup: Exit Candidate; select keep-data removal, then
install. Verify saved configuration starts blue. To exercise first-save yellow
→ blue and full removal, use disposable configuration in an authorized test
installation: select full removal, confirm, verify both dedicated roots/native
entries absent, reinstall, save a valid provider and observe blue without
restart. Full removal permanently deletes real keys/data if selected. Also
test Windows Installed Apps removal's default/Cancel/full choices. Downloaded
Setup files and Windows-owned event/Prefetch/Defender records are outside scope.
