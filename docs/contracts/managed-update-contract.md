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
| `request` | `installed_version`, `target_version`, `bundle_path`, `install_root`, `shared_root`, `managed_install_id` |
| `handoff_ready` | `candidate_root`, `candidate_python`, `manifest_sha256`, `expected_version` |
| `launch_receipt` | `launch_attempt_id`, `expected_version`, `executable_path`, `process_id` |
| `startup_health` | `launch_attempt_id`, `expected_version`, `actual_version`, `executable_path`, `healthy` |
| `result` | `outcome` (`updated`, `rolled_back`, `failed`), `active_version`, `failure_code`, `rollback_failure_code` |

No artifact may infer identity from a filename. `startup_health` is accepted
only when transaction, launch attempt, expected version, actual version, and
the resolved executable inside the committed version all match.

## Transaction state machine

Legal forward transitions are `verify -> prepare -> shutdown -> commit ->
launch -> health -> finalize`. A failure before commit finalizes with the old
pointer unchanged. A failure at or after commit transitions to `rollback`,
atomically restores the old pointer, launches that version, requires matching
health, then finalizes as `rolled_back`. Journal writes precede each side
effect and settlement is exactly once.

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
access and machine truststore injection are disabled.

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

## Update eligibility

Apply is eligible only when a signed managed-install marker supplies a valid
`managed_install_id`; current pointer, resolved executable, installed metadata,
and version manifest agree under one install root; no editable `direct_url.json`
or `.git`/worktree evidence exists; shared `ApplicationPaths` are outside the
immutable version tree; and the update mutex is held. Unknown identity is
check-only and fails closed for apply.
