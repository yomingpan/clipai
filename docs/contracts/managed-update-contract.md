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
| `request` | `installed_version`, `target_version`, `installed_executable`, `bundle_path`, `bundle_size`, `bundle_sha256`, `manifest_sha256`, `key_id`, `install_root`, `shared_root`, `managed_install_id` |
| `handoff_ready` | `candidate_root`, `candidate_python`, `manifest_sha256`, `expected_version` |
| `launch_receipt` | `launch_attempt_id`, `expected_version`, `executable_path`, `process_id` |
| `startup_health` | `launch_attempt_id`, `expected_version`, `actual_version`, `executable_path`, `healthy` |
| `result` | `outcome` (`updated`, `rolled_back`, `failed`), `active_version`, `failure_code`, `rollback_failure_code` |

No artifact may infer identity from a filename. `startup_health` is accepted
only when transaction, launch attempt, expected version, actual version, and
the resolved executable inside the committed version all match.
`bundle_size` is a positive catalog-bound admission limit checked before the
bundle is read or extracted.

## Transaction state machine

Legal forward transitions are `verify -> prepare -> shutdown -> commit ->
launch -> health -> finalize`. A failure before commit finalizes with the old
pointer unchanged. A failure at or after commit transitions to `rollback`,
atomically restores the old pointer, launches that version, requires matching
health, then finalizes as `rolled_back`. Journal writes precede each side
effect and settlement is exactly once.

`journal.json` is an atomic latest-intent record with `schema_version: 1`,
`journal_kind: clipai-managed-update-journal-v1`, monotonic `revision`, exact
transaction/version identity, `phase`, and nullable `failure_code`. The journal
is written before every phase side effect and rejects skipped transitions.

`FailureCode` values are stable machine codes grouped as `identity_*`,
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

## Signing

Manifests are signed with Ed25519 over canonical UTF-8 JSON bytes under
namespace `clipai.managed-update.manifest.v1`. Production trusts pinned public
keys identified by `key_id`; private keys never enter bundles or the repo.
Tests use only `clipai-managed-update-test-v1` fixtures and must reject that key
identity in production policy. Rotation adds a new pinned public key before old
key retirement; revocation requires a new application release.

## Catalog

`catalog.json` requires `schema_version: 1`, `catalog_kind`, `channel`,
`generated_at`, and `releases`. `catalog_kind` is `clipai-managed-update-v1`.
Each release requires `version`, `bundle_url`, `bundle_sha256`, `bundle_size`,
`manifest_sha256`, `key_id`, and `minimum_launcher_version`. Stable policy
rejects prereleases, downgrade/equal versions, duplicate versions, non-HTTPS
remote URLs, and inconsistent asset/manifest identities.

## Cross-process CLI

One dispatcher exposes `install`, `launch`, `host`, and `selfcheck`. Shared
arguments retain their exact names and semantics:

- `--shared-root`: absolute root for user data and transaction artifacts.
- `--transaction-id`: exact `TransactionId` for request/journal/artifacts.
- `--install-root`: absolute managed install root.
- `--launch-attempt-id`: exact attempt written into launch/health receipts.
- `--expected-version`: exact version the launched distribution must report.

Missing, relative, malformed, or conflicting values fail before side effects.
The dispatcher converts argv into one of four immutable core command models and
crosses one `execute(command)` composition seam; subcommands do not own separate
entry scripts or duplicate parsing.
Launch uses the exact committed `.venv/Scripts/python.exe` and signed manifest
entrypoint, passes all six identity/root arguments, and strips inherited
`VIRTUAL_ENV`, `PYTHONPATH`, and `PYTHONHOME`. Health is accepted only from the
same attempt and executable; a stale attempt is ignored until the bounded
12--20 second external health budget expires.

## Update eligibility

Apply is eligible only when the stable installer-created managed-install
receipt supplies a valid `managed_install_id`; current pointer, resolved
executable, installed metadata, and publisher-signed version manifest agree
under one install root; no editable `direct_url.json` or `.git`/worktree
evidence exists; shared `ApplicationPaths` are outside the immutable version
tree; and the update mutex is held. Unknown identity is check-only and fails
closed for apply.

`managed-install.json` uses `schema_version: 1`, `marker_kind:
clipai-managed-install-v1`, `managed_install_id`, canonical `install_root` and
`shared_root`, `launcher_version`, and `key_id`. It is a local install receipt,
not a publisher signature: the stable `install` command may create it only
after verifying the initial version's signed manifest. `install-state.json`
uses `schema_version: 1`, `state_kind: clipai-managed-install-state-v1`, the
same install identity, monotonic `revision`, `current_version`, and nullable
`previous_version`. Versions resolve only as `install_root/versions/{version}`.
An existing target version root is never replaced unless its exact sibling
`versions/.{target}.candidate-owner.json` names the same transaction and target
version. Prepare copies only from the already verified staging tree, verifies
the copied inventory again, and removes the reservation only after candidate
executable/version proof succeeds.
