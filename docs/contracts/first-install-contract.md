# First install contract

Status: local acceptance implementation, 2026-10-01, following the user's
instruction to complete an installable candidate. Core/services coordination,
admitted filesystem work and Windows adapters are implemented. Public-release
prerequisites and clean-VM/new-user evidence remain open. The isolated unsigned
ClipAI Preview candidate is not an official release. See [the plan](../specs/first-install-installer-plan.md)
and [ADR-0020](../adr/0020-first-install-bootstrap-and-recovery.md).

## Owners and preserved mechanisms

- `FirstInstallCoordinator` is the services owner of first-install
  admission, snapshot, cancellation decision and recovery policy. Its inputs
  and results are typed immutable core models. It does not import Inno Setup,
  subprocess, filesystem, Windows registry or concrete verifier code.
- The existing filesystem installer, bundle stager, payload materializer and
  candidate builder remain the single owners of their mechanisms. Do not
  recreate manifest parsing, pip commands or version-pointer policy in Setup.
- App composes a focused installation backend and dispatches typed intents.
  Windows integration owns shortcut, uninstall registration and native process
  operations. Setup owns display and explicit command submission only.
- `ManagedUpdateGate` remains the exclusive mutation admission seam for one
  canonical install root. The installation backend opens one admitted
  operation context, holds the existing lease through integration/settlement,
  and exposes typed operation-bound prepare, commit, integrate and cleanup
  results to services. Closing the context releases the lease.
- The existing installer's lease-bound work is exposed by `open_install`:
  its public install entry still acquires the gate, while an
  already-admitted backend uses that same work without reacquiring. Do not
  introduce nested acquisitions or a second ungated installation path. Tests
  must prove all write entry points require the same valid operation context.

This is deployment policy, not a Workflow. Reuse `TransactionId` for the
installation transaction; `managed_install_id` identifies the installation,
and launch uses the existing separate `LaunchAttemptId`. A projection revision
never grants permission to mutate files or launch an app.

## Admission and fixed locations

V1 uses Windows x64, per-user installation, no PATH changes and no autostart.
The proposed default roots are `%LOCALAPPDATA%/Programs/ClipAI` and
`%LOCALAPPDATA%/ClipAI`; managed `ApplicationPaths` already accept the shared
root, keep secrets/state outside version payloads and must be injected before
runtime composition. Reject equal, nested, redirected or ambiguous roots;
never infer deletion authority merely from the string prefix of a path.
The acceptance candidate uses separate `ClipAI Preview` roots and a separate
Start Menu/uninstall identity. It accepts Windows 11 x64 only (`x64os`).

Setup embeds trusted bootstrap code, runtime/tools, production keyring and
fixed release identity. App composition resolves the installed verifier by
its admitted fixed location, not the user's PATH. Runtime and verifier remain
outside immutable version roots, available for the lifetime of all venvs.
The source Python installer, Tcl/Tk, ensurepip and native dependencies need
actual archive/hash/license admission before any production runtime is chosen.

Bootstrap has a focused app composition entrypoint that imports the shared
install engine without composing the desktop runtime. The existing `main.py`
eagerly imports desktop dependencies; it is not a proven minimal bootstrap.
The exercised engine path needs `packaging` in addition to the standard library;
admit its exact distribution/hash/license with the bootstrap. A developer
snapshot passing a synthetic bundle is compatibility evidence only, not a
production dependency closure or an authenticated bootstrap distribution.

Final native signing admission includes the venv redirectors under
`Lib/venv/scripts/nt`, not only the top-level Python executable or Setup.
The current builder copies these into launcher/version venvs. Record upstream
source identity separately from final signed artifact identity: signing changes
file bytes, so regenerate and verify affected final hashes before sealing the
Setup. Keep notices attached to the admitted component profile; file presence
alone does not establish complete component/license mapping.

The gate now uses `Global\\ClipAI.ManagedUpdate.v1.<canonical-root-hash>` with
the current user's default Windows token DACL. All bundled candidate writers
use this same gate. Local non-admin use is exercised; cross-logon-session and
other-user access require device proof. Older deployed writers using `Local\\`
do not contend with this namespace. A public migration must prevent mixed
old/new writers against one root; the isolated Preview root has no old writer.
Do not add an independent file lock or silently allow mixed namespaces.
The persisted transaction record is recovery evidence, not another live lock.

## Durable operation evidence

Before payload or runtime writes, gate-protected admission reserves the target
and writes an atomic `initial-install` record under the existing transaction
root. It binds transaction/install identity, canonical roots, fixed release
identity, phase and a bounded set of owned paths/integration receipts. This is
local ownership evidence, not a new content manifest or independent registry.
The adapter-local v1 owner receipt enumerates exact private directories/files,
native integration identity, writer PID/executable, phase and elapsed time.
It remains local filesystem evidence, not a cross-layer raw-dictionary API.

Creating the empty target/record storage can precede the durable record. A crash
in that interval deliberately leaves unknown ownership and fails closed; it
must not authorize automatic removal. Reject nonempty unknown targets rather
than adopting them. Persist intent before each mutation and reconcile actual
marker/integration evidence after a crash. Keep ownership proof until cleanup
or integration completes. Default removal never deletes the shared root or
unknown user files. The separately selected full-removal intent below grants
deletion authority only over the proven dedicated ClipAI shared data root.

All existing-target checks repeat under the lease. A cleanup first proves the
old writer and its children stopped, then removes only that record's artifacts.
An older completion/cancellation cannot affect a newer admitted transaction.
Cancel and retry are typed user intents, not consequences of closing a view.

## Commit, cancellation and visible truth

| Phase/result | Contract |
| --- | --- |
| Checking, verifying, preparing | Immediate pending projection; no fabricated percentage. Cancellation prevents further work and settles only after owned work stops and cleanup completes or fails. |
| Commit critical section | Persist commit intent; state and marker publication are a bounded non-cancellable section. Defer cancellation until actual marker evidence is reconciled. |
| Marker absent after failure | Clean only admitted owned artifacts. Report `failed`, `cancelled` or `cleanup_failed`; a surviving unknown/unsafe artifact blocks retry. |
| Marker present, integration incomplete | Report `installed_integration_incomplete`; retain a trusted maintenance entry and receipt. Complete or compensate shortcuts/registration without deleting committed payload or recreating venvs. |
| Marker and required integration ready | Report `installed`. Cancel after this point means installed and not launched, not an uninstalled/cancelled transaction. |
| Explicit launch | Use existing current-version resolution and matching startup health. Launch failure does not undo install success. Provide retry, diagnostics and maintenance path. |
| Provider not configured | Show first-use setup readiness independently. Installation and startup health do not wait for provider credentials or send provider requests. |

The first-install result vocabulary does not change existing managed
update result types. Core models and tests are added together; adapters report
evidence, services decide terminal policy, UI only projects it.

## Integration, uninstall and maintenance

Shortcuts target the stable launcher. One Windows adapter owns the shortcut
and uninstall registration receipts; Inno Setup's original file inventory
cannot become the authority for dynamically added managed versions.

Uninstall acquires the same installation gate and re-proves install identity.
An active updater makes uninstall busy; V1 offers retry instead of inventing
forced cancellation across entry points. New launch admission cannot enter
an installation being removed. Preview refuses removal while a process uses
its private Python runtime; it asks the user to exit and retry rather than
terminating applications. Inability to prove idle is terminal failure.

Remove only proven owned versions, launcher, private tools and integration
entries. Shared API keys, preferences and user data are retained by default;
deletion is a separate explicit intent with an enumerated owned scope. Shared
WebView2/.NET/VC prerequisites are never removed as ClipAI-owned files.
Native integration ownership is checked before program files are removed.
Failed removal preserves ownership. The same Setup's temporary trusted engine
is the retry entry even if installed maintenance files have already been
removed. Control Panel copies the maintenance runtime outside the install
root before removal. A bounded OS supervisor waits for the helper process to
exit and removes only that exact, generated helper directory before showing
success. Cleanup failure is visible; it never terminates a user process or
sweeps other temporary directories. Clean-VM self-removal remains pending.

The quiet helper projects the existing coordinator's terminal `UninstallSnapshot`
into `maintenance-result.json` only when explicitly launched with
`--maintenance-result`. The freshly generated helper owns that result path;
the supervisor accepts a regular, non-redirected file of at most 1 KiB with
schema version 1, terminal phase and bounded exception-class code only.
No raw subprocess output, traceback, credentials or user content is persisted.
Worker exit code and terminal phase must both prove removal before success,
and exact-helper cleanup must also finish. Busy removal, other removal failure
and helper cleanup failure have distinct terminal feedback. A missing,
malformed or contradictory projection fails closed. A busy result with successful
helper cleanup must not claim cleanup failed; ask the user to exit the tray and
close remaining startup error windows. The idle gate is never bypassed.

Both Setup and Windows/Start Menu removal offer keep-data (default) and
full-removal choices. Full removal explicitly warns that settings, API keys,
history, logs, caches and custom ClipAI content are permanently deleted and
requires confirmation. `UninstallIntent.delete_user_data` is carried unchanged
through the existing coordinator/backend/helper; merely opening the screen
does not authorize deletion. Quiet automation requires explicit
`--delete-user-data` (Setup: `/REMOVE=1 /DELETEUSERDATA=1`).

Full removal re-proves native identity and the existing installation gate,
requires the dedicated `%LOCALAPPDATA%/Programs/<product>` and
`%LOCALAPPDATA%/<product>` pair, rejects redirected roots/descendants, unknown
program files and records belonging to another installation. Native writes
settle before shared-root deletion, so no final retained-data record recreates
the directory. A cleanup failure reports failure and retains owner proof for
retry with the same Setup. Deletion is not transactional: already-deleted data
cannot be restored after a later failure. Do not claim retained data in that
failure screen. Windows-owned Prefetch/event/Defender records, user-downloaded
Setup files, manually exported files and shared prerequisites are outside this
owned scope; the UI must not promise to erase every trace on the computer.
Setup does not generate an anonymous persistent log by default. Explicit
`/LOG` diagnostics are caller-owned, like manually exported diagnostics.

V1 maintenance is a trusted retained-data uninstall followed by a compatible
new Setup. It must work when the app/version venv is broken and cannot depend
on that broken venv. Do not overwrite a live shared base Python in place.
Future incompatible data blocks reactivation without deleting or resetting
the data. Define an explicit data migration contract when such a release is
actually needed; V1 introduces none.

## Diagnostics, compatibility and safeguards

An owned running application blocks removal with the safe typed
`InstallationBusyError`; no program files or native receipts are removed.
Setup completion content is projected after Inno's stock completion text is
initialized, at the finished-page boundary (and final step for silent runs).
Removal success, removal failure and install success are distinct. Finish only
closes Setup. A failed engine keeps exit code 100 and never offers Launch.

Preview Setup, Start Menu shortcuts and the uninstall registration use the
shipped ClipAI icon. Installation creates a desktop shortcut by default using
the Windows Desktop known folder (including redirection). Windows integration
records its desktop path in the installation's registry receipt and verifies
target and arguments before removal. Existing desktop shortcuts are never
overwritten. Older installations without that receipt do not own a desktop
shortcut and cannot delete one during removal.

Capture transaction identity, stage, bounded elapsed time, exit/error code and
sanitized cause. Do not preserve raw credential-bearing environments or
unbounded subprocess output. Diagnostics export is an explicit intent and
works even if installation never reaches startup.

The release maintainer owns runtime, verifier, keyring and launcher security
maintenance. Pin the actual Python minor/ABI and native wheel support for each
candidate in the release inputs; `python_requires` alone is not a wheel ABI
guarantee. Preserve the existing signed managed schema; no latest-at-install
resolution and no downloaded keyring trust expansion.

Required enforcement in B/C: core/services import boundaries; one stager and
materializer; one gate, including multiple processes/logon sessions; checks
under admission; ownership-before-write/crash boundaries; no deleting newer
operations; marker/integration partial settlement; cancellation around commit;
updating-versus-uninstall; broken-venv maintenance; retained-data reinstall.
Unit/fault tests are policy evidence. Clean-VM setup/reboot/update/uninstall,
browser download trust and real first-use results are separate device gates.

## Release packaging seam (2026-10-04)

`scripts/build_setup_release.py` composes `SetupReleaseBuilder` with an injected
environment. It consumes one existing bundle, one fixed catalog/public keyring,
and the reviewed `packaging/windows/setup-inputs.json` archive/compiler inventory.
It does not resolve dependencies, build an app wheel, sign a manifest or generate
a trust key. The existing `VerifiedManagedBundleStager` alone admits the managed
bundle against catalog size/hash, manifest signature/version/key and inventory.
Generic archive extraction is limited to pinned upstream bootstrap archives and
wheels from that admitted tree; it is not another managed-bundle admission path.

The bootstrap package, `packaging`, `cryptography`, `cffi` and `pycparser` come from those exact wheels,
not the checkout. The CLI compares all first-party wheel code/resources and
shipped payload to the declared Git commit, allowing only Git text newline
conversion. Official packaging also checks the actual tag points to that commit.
Technical candidates label their tag as unverified and use `ClipAI Candidate`
roots/native identity, independent of both Preview and ordinary installations.

The shared thin wizard is `packaging/windows/setup.iss`; the Preview path is a
compatibility include with unchanged product/location defaults. Fixed bundle and
keyring hashes are compiled into candidate Setup and checked on actual extraction
before installation. `/VERIFYONLY=1` requests payload proof only and cannot launch,
install or remove an app; its visible completion says verification completed.

Provenance records source/tag, distinct app/launcher/runtime/verifier/compiler
identities, wheel/lock/bundle/Setup hashes, wizard/packaging adapter hashes and
the entire staged inventory. Unsigned provenance is build evidence, not a new
trust authority. `verify_packaged_app` uses the existing materializer/builder with
the exact admitted lock and proves imports stay in installed site-packages under
isolated Python. `verify_setup_extraction` proves the compiled EXE's bundle bytes;
neither is clean-VM or reboot evidence.

`distribution_admission=pending` blocks official packaging. The explicit
technical-candidate mode preserves production signature/keyring validation but
does not authorize public distribution. Native/license admission, the explicitly
selected publisher policy, clean VM, first-use observation and direct publication
authorization remain independent gates. 3.7.18 replaces the runtime OpenSSH
Preview input with the pinned cryptography SSHSIG profile. Do not change the admission label without the
component/license/security review described in the release runbook.

The platform `Ed25519ManifestVerifier` is the single canonical-manifest and
SSHSIG admission owner. It uses cryptography's Ed25519 primitive with a bounded
SSHSIG v1/Ed25519 envelope, exact trusted public key and namespace, SHA-256 or
SHA-512, and rejects trailing/truncated data. No runtime executable, PATH lookup,
temporary allowed-signers file or fallback verifier is used. Build-time signing
remains OpenSSH. Setup extracts verifier dependency wheels only from the admitted
bundle and checks the pinned cryptography version; offline bootstrap and installed
app smoke must import those exact native dependencies and verify a real manifest.

For 3.7.18 the maintainer selected unsigned Windows Setup with no paid signing
service. The release verifier requires explicit unsigned acceptance and actual
`NotSigned` status of the final hash. This changes only publisher policy; official
managed content signatures, native/license admission and device gates remain.
