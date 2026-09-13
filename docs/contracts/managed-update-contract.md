# Managed update contract (schema version 1)

This is the executable interface baseline for ADR-0017. JSON objects reject
unknown fields. IDs are non-empty opaque ASCII strings (maximum 128 chars),
versions are normalized PEP 440 strings, paths are absolute, and timestamps are
UTC RFC 3339 strings.

## Artifact envelopes

Every artifact has `schema_version: 1`, `artifact_kind`, `transaction_id`, and
`created_at`.

| `artifact_kind` | Required payload fields |
| --- | --- |
| `request` | `installed_version`, `target_version`, `installed_executable`, `installed_process_id`, `bundle_path`, `bundle_size`, `bundle_sha256`, `manifest_sha256`, `key_id`, `install_root`, `shared_root`, `managed_install_id` |
| `handoff_ready` | `candidate_root`, `candidate_python`, `manifest_sha256`, `expected_version` |
| `launch_receipt` | `launch_attempt_id`, `expected_version`, `executable_path`, `process_id` |
| `startup_health` | `launch_attempt_id`, `expected_version`, `actual_version`, `executable_path`, `healthy` |
| `result` | `outcome` (`updated`, `rolled_back`, `failed`), `active_version`, `failure_code`, `rollback_failure_code` |

No artifact may infer identity from a filename. `startup_health` is accepted
only when transaction, launch attempt, expected version, actual version, and
the resolved executable inside the committed version all match.
`bundle_size` is a positive catalog-bound admission limit checked before the
bundle is read or extracted.
`installed_process_id` is captured by the running app; the external host opens
and verifies that process and its executable before preparation, then waits on
the retained process handle after `handoff_ready` causes normal app shutdown.
The host requests `SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION`, compares
the complete `QueryFullProcessImageNameW` path, and never substitutes basename,
substring, or later PID polling for the retained handle.

## Transaction state machine

Legal forward transitions are `verify -> prepare -> shutdown -> commit ->
launch -> health -> finalize`. A failure before commit finalizes with the old
pointer unchanged. Before shutdown, the backend supplies the exact known-good
version root. Once shutdown completes, every later failure transitions to
`rollback`: a commit failure relies on the atomic pointer remaining unchanged,
while a post-commit failure atomically restores it. Both paths launch that
known-good root and require matching health before settling as `rolled_back`.
Journal writes precede each side effect and settlement is exactly once.

If a host terminates without a terminal result, recovery does not infer that a
pre-recorded side effect completed. It records a re-entrant
`rollback(update_interrupted)` intent, verifies the signed installed version,
atomically restores the pointer only when it currently names the target, and
launches that known-good version. Recovery settles `rolled_back` only after
matching health; another interruption may repeat the rollback intent safely.
On normal stable-launcher startup, the shared transaction root is scanned for
request+journal pairs without a result. Exactly one is recovered before any
ordinary current launch; multiple incomplete transactions fail closed instead
of choosing an order. A successful recovery already launches the known-good
application, so the stable launcher does not launch it a second time.

`journal.json` is an atomic latest-intent record with `schema_version: 1`,
`journal_kind: clipai-managed-update-journal-v1`, monotonic `revision`, exact
transaction/version identity, `phase`, and nullable `failure_code`. The journal
is written before every phase side effect and rejects skipped transitions.

`FailureCode` values are stable machine codes grouped as `identity_*`, `update_*`,
`catalog_*`, `download_*`, `signature_*`, `bundle_*`, `prepare_*`,
`shutdown_*`, `commit_*`, `launch_*`, `health_*`, `rollback_*`, and
`internal_error`. Diagnostics may add detail but must not replace the code.

## Managed bundle

The release asset is a ZIP whose every member starts with
`clipai-managed-v1/`. It contains exactly one payload tree plus:

```text
clipai-managed-v1/
  payload/
  wheelhouse/
  requirements.lock
  install-manifest.json
  install-manifest.json.sig
```

`install-manifest.json` requires `schema_version`, `app_version`,
`bundle_format`, `entrypoint`, `python_requires`, `requirements_lock_sha256`,
`files` (relative path, size, sha256, role), `signing_namespace`, and `key_id`.
Paths must be normalized, unique, contained, and must not name `.env`, `.git`,
`.venv`, `data`, `logs`, `diagnostics`, launcher, updater, or update journal.
Candidate installation uses only `requirements.lock` and `wheelhouse/`; network
access and machine truststore injection are disabled. Admission compares the
catalog-bound compressed size and hash before extraction, caps total
uncompressed size, then verifies manifest hash, signature, and complete file
inventory before candidate preparation.

Candidate preparation invokes the clean base interpreter as `python -I -m
venv --without-pip`, seeds bundled pip by invoking the new venv Python directly
as `python -I -m ensurepip`, then invokes that same Python as `python -I -m pip
--isolated install --no-index --require-hashes --find-links wheelhouse -r
requirements.lock`. Splitting pip seeding from `venv` is required because
Windows `venv` cannot reliably re-exec `ensurepip` from a `\\?\` target even
though the prefixed candidate Python itself is directly launchable. Its
injected environment removes inherited
`VIRTUAL_ENV`, `PYTHONPATH`, `PYTHONHOME`, and index overrides, sets
`PYTHONNOUSERSITE`, disables pip input/version checks, and points
`PIP_CONFIG_FILE` at the platform null device so machine/user pip and
truststore injection cannot participate. The managed-bundle harness builds a
minimal pinned wheelhouse with the clean base Python, runs preparation with
poisoned parent variables, launches the manifest file entrypoint, and accepts
only matching attempt, version, and candidate-venv executable health evidence.
Candidate executable evidence is compared through the shared canonical path
boundary so `\\?\` and ordinary spellings of the same Windows file are one
identity, never a basename or substring match.

Bundle admission has one platform owner shared by initial install and update.
Its typed input is the contained transaction root plus expected bundle size,
bundle SHA-256, manifest SHA-256, version, and key identity; its output is an
immutable verified staging root with the parsed manifest. Callers may copy or
build only from that staging root, never from the admitted archive again.

## Signing

Manifests are signed with Ed25519 over canonical UTF-8 JSON bytes under
namespace `clipai.managed-update.manifest.v1`. Production trusts pinned public
keys identified by `key_id`; private keys never enter bundles or the repo.
Tests use only `clipai-managed-update-test-v1` fixtures and must reject that key
identity in production policy. Rotation adds a new pinned public key before old
key retirement; adding or revoking trust requires a new stable-launcher release.

The stable launcher root owns `managed-update-trusted-keys.json`; versioned
payloads and downloaded bundles cannot replace it. Its exact schema is
`schema_version: 1`, `keyring_kind: clipai-managed-update-trusted-keys-v1`, and
`keys`, a non-empty array of exact `{key_id, algorithm, public_key, key_kind}`
objects. `algorithm` is `ssh-ed25519`; `key_kind` is `production` or
`test_fixture`; key identities are unique. Only the reserved
`clipai-managed-update-test-v1` identity may be a test fixture, and production
composition excludes all test-fixture keys unless test policy is explicitly
injected.

## Catalog

`catalog.json` requires `schema_version: 1`, `catalog_kind`, `channel`,
`generated_at`, and `releases`. `catalog_kind` is `clipai-managed-update-v1`.
Each release requires `version`, `bundle_url`, `bundle_sha256`, `bundle_size`,
`manifest_sha256`, `key_id`, and `minimum_launcher_version`. Stable policy
rejects prereleases, downgrade/equal versions, duplicate versions, non-HTTPS
remote URLs, and inconsistent asset/manifest identities.
Catalog transport accepts only credential-free HTTPS URLs, sends an explicit
ClipAI User-Agent and JSON Accept header, uses a 12-second request budget, and
reads at most 1 MiB. HTTP/network failures are `catalog_unavailable`; invalid
URLs, redirect targets, status, lengths, or oversized bodies are
`catalog_invalid`. Schema and release selection remain owned by the catalog
parser after transport admission.
Bundle transport accepts the catalog-admitted credential-free HTTPS URL plus
the exact expected compressed size and SHA-256, uses a 20-second network
budget, and streams bounded chunks into a same-directory temporary file through
`managed_update_fs`. A present Content-Length must equal the catalog size; the
streamed size and digest must always match before atomic replace. Any network,
filesystem, length, or digest failure is `download_failed` and preserves an
existing destination.

The single verification harness advances cumulatively through `fast`,
`synthetic`, `loopback-http`, and `managed-bundle`. The loopback stage starts a
real local HTTP server but keeps catalog and bundle identities HTTPS-only: a
test-only opener redirects an already-admitted loopback request to that server,
without changing production URL policy. It builds with the reserved ephemeral
test Ed25519 identity, performs real catalog and streaming bundle requests, and
proves both successful signature admission and fail-closed signature tampering.

## Cross-process CLI

One dispatcher exposes `install`, `launch`, `host`, and `selfcheck`. Shared
arguments retain their exact names and semantics:

- `--shared-root`: absolute root for user data and transaction artifacts.
- `--transaction-id`: exact `TransactionId` for request/journal/artifacts.
- `--install-root`: absolute managed install root.
- `--launch-attempt-id`: exact attempt written into launch/health receipts.
- `--expected-version`: exact version the launched distribution must report.

Missing, relative, malformed, or conflicting values fail before side effects.
`--shared-root` is already the effective root for that managed instance;
launch composition derives state, secrets, logs, diagnostics, and update paths
from it without applying `CLIPAI_INSTANCE_NAME` a second time.
The dispatcher converts argv into one of four immutable core command models and
crosses one `execute(command)` composition seam; subcommands do not own separate
entry scripts or duplicate parsing.
The app composition root supplies one typed command executor to that seam.
`install` returns success only after the verified candidate, revision-zero
state, and managed marker are durable; it does not implicitly launch the app.
`launch` alone enters the application runtime, and `host` alone owns an update
transaction. Command-specific dependencies are composed lazily so a launch
does not require signing tools or a trusted-key file.
`selfcheck` is read-only and returns zero only when the current pointer resolves
to a signed manifest whose install identity, exact version-root venv Python,
distribution metadata, non-editable provenance, and entrypoint all agree. It
does not repair, switch, launch, or mutate install or user state; malformed or
incomplete evidence fails closed with a non-zero result.
Normal managed startup is not a fifth subcommand. The stable launcher resolves
and verifies the atomic current pointer, creates a fresh startup transaction and
launch attempt, starts that exact version through the same `launch` CLI contract,
and returns success only after matching startup health. The versioned process
never reads or chooses the current pointer.
For `host`, command roots and transaction identity must match the request before
an installed-process handle is acquired. The host retains that verified handle
through transaction settlement, writes exactly one `result` artifact, and then
closes it. Exit status is zero only for `updated`; `rolled_back` and `failed`
return non-zero because the requested update did not complete.
Launch uses the exact committed `.venv/Scripts/python.exe` and signed manifest
entrypoint, passes all six identity/root arguments, and strips inherited
`VIRTUAL_ENV`, `PYTHONPATH`, and `PYTHONHOME`. Health is accepted only from the
same attempt and executable; a stale attempt is ignored until the bounded
12--20 second external health budget expires. A healthy receipt is emitted
only after every runtime start component succeeds and immediately before the UI
event loop; a construction or start failure emits no healthy receipt.
An actual/expected version mismatch writes an unhealthy receipt and does not
enter the runtime; readiness for one launch attempt is emitted at most once.

## Installed-app preparation and handoff

Services owns discover-to-request coordination behind a `ManagedReleaseSource`
port. Its immutable input contains the proven managed install/version/launcher
identity plus the actual executable and process ID. No available release
returns no request and performs no download. An available release is downloaded
into that transaction's shared artifact root, then produces one exact
`UpdateRequestArtifact` from the catalog identity and downloaded path. Services
does not write artifacts, spawn the host, or stop the runtime; app composition
owns those lifecycle effects after receiving the request.

The platform handoff client atomically publishes that request, starts the stable
launcher `host` command in an isolated environment, and waits at most 20 seconds
for either terminal `result` or matching `handoff_ready` evidence. Readiness must
match transaction, target version, manifest digest, exact candidate version root,
and exact candidate venv Python. Host exit, malformed or mismatched evidence, and
timeout fail as typed `handoff_*` codes. The app executor requests normal runtime
shutdown only after matching readiness; no-update and every handoff failure leave
the installed process running.

## Update eligibility

Apply is eligible only when the stable installer-created managed-install
receipt supplies a valid `managed_install_id`; current pointer, resolved
executable, installed metadata, and publisher-signed version manifest agree
under one install root; no editable `direct_url.json` or `.git`/worktree
evidence exists; shared `ApplicationPaths` are outside the immutable version
tree; and the update mutex is held. Unknown identity is check-only and fails
closed for apply.

One Windows session named mutex serializes mutation per canonical install root.
Its name is `Local\\ClipAI.ManagedUpdate.v1.{sha256}`, where the digest is over
the case-folded canonical install-root path. Initial install holds the lease
from before bundle admission until marker publication or cleanup. Host reads
and matches the request first, then holds the lease from before process-handle
acquisition through terminal result publication. Contention fails immediately
as `update_busy`; closing or process death releases the lease. Read-only
`selfcheck` does not acquire it.

`managed-install.json` uses `schema_version: 1`, `marker_kind:
clipai-managed-install-v1`, `managed_install_id`, canonical `install_root` and
`shared_root`, `launcher_version`, and `key_id`. It is a local install receipt,
not a publisher signature: `key_id` records the bootstrap release key but does
not pin every later release to that key. The stable keyring verifier alone owns
current/request manifest trust and therefore permits pre-published key rotation.
The stable `install` command may create the marker only after verifying the
initial version's signed manifest. `install-state.json`
uses `schema_version: 1`, `state_kind: clipai-managed-install-state-v1`, the
same install identity, monotonic `revision`, `current_version`, and nullable
`previous_version`. Versions resolve only as `install_root/versions/{version}`.
Initial install first atomically copies its external archive into the
transaction root, admits it through the shared bundle stager, and builds the
complete candidate. From that same verified staging tree it also builds the
fixed `install_root/launcher` environment and atomically copies the installer's
trusted public-key file there. The launcher is never selected by or stored
inside the current-version pointer. It then publishes revision-zero state
followed by the managed marker; neither control file may exist before both
environments and the keyring are proven, and an existing marker, state, target
version, or launcher is never overwritten.
An existing target version root is never replaced unless its exact sibling
`versions/.{target}.candidate-owner.json` names the same transaction and target
version. Prepare copies only from the already verified staging tree, verifies
the copied inventory again, and removes the reservation only after candidate
executable/version proof succeeds.
