# ADR-0017: Managed update transaction

Status: accepted, 2026-09-13.

## Decision

ClipAI managed updates use immutable side-by-side version directories, shared
user data, and a stable launcher/updater outside every version directory. The
services owner advances one transaction through `verify -> prepare -> shutdown
-> commit -> launch -> health -> rollback | finalize`. Platform adapters own
catalog transport, signature verification, filesystem artifacts, candidate
environment construction, and process lifecycle. App is the only composition
layer.

`CandidateEnvironmentBuilder` and `ManagedApplicationLifecycle` are typed seams
with production and test adapters. All low-level update paths, prefixed ZIP
handling, containment checks, and atomic JSON writes go through
`ClipAI.platform.managed_update_fs`.

## Invariants

- A request, handoff, launch receipt, startup health receipt, and result are
  correlated by `TransactionId`; launch and health also require the exact
  `LaunchAttemptId` and expected version.
- Commit changes only the small current-version pointer. The previous version
  remains intact until matching startup health succeeds.
- Any failure after commit attempts rollback and relaunches the previous known
  good version. Failure to prove a launchable old or new version is terminal.
- Versioned payloads never own config overrides, secrets, state, logs, or
  diagnostics. `ApplicationPaths` is injected before update code is composed.
- Apply fails closed outside a proven managed installation.

## Consequences and review trigger

Release creation has one signing/manifest core and thin payload assembly; the
managed CLI has one dispatcher. One verification harness grows through
synthetic, loopback HTTP, and offline managed-bundle stages. Review this ADR if
a second transaction owner, filesystem helper, release builder, managed entry
shim, or user-data migration path is proposed.
