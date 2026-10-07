# Update and installation architecture diagnosis

Baseline: `88ed260`. Scope: managed update, downloadable Setup and release tooling.

1. **Judgment: Yellow; local refactor; high confidence.** Preserve the verified
   update/install engine and delete duplicated packaging and repeated work.
   This is not an engine migration.
2. **Evidence:** `build_preview.py` had 161 lines implementing checkout bootstrap
   copies, app wheel construction, lock generation, local signing and Setup
   compilation. No executable callers were found in imports, tests, scripts or
   workflows; only experimental/historical documentation referred to it.
   `SetupReleaseBuilder` extracted runtime then copied it to stage.
   `ManagedInstallLayout._prove_version` inventoried all site-packages twice.
   `verify_managed_update` ran synthetic E2E after the default unit suite already
   included it. These are source observations, not reproduced user failures.
3. **Protected behavior:** signed bundle admission, offline hashed dependencies,
   operation-scoped gate and durable ownership, current-pointer commit, matching
   launch health, rollback, retained-data uninstall/reinstall, typed About intent,
   source-install ineligibility and native Unicode shortcuts.
4. **Diagnosis:**
   - Ownership: `ManagedReleaseBuilder` owns bundle construction;
     `SetupReleaseBuilder` owns fixed-input packaging; `ManagedInstallLayout`
     owns eligibility; `verify_managed_update` owns staged validation.
     `ManagedUpdateTransaction` and `FirstInstallCoordinator` retain their
     distinct lifecycle policy.
   - Capability: the same installation and packaging capability serves official
     and technical candidates. A checkout-copying Preview path is a superseded
     special case.
   - Propagation: the Preview implementation duplicated build/trust knowledge
     across the packaging seam. The two scans duplicated distribution discovery.
     The release harness duplicated suite selection.
   - Enforcement: architecture test prevents the old parallel builder returning;
     archive fault tests validate even excluded members; public eligibility tests
     reject invalid metadata; harness behavior tests prove coverage and failure
     propagation, including real default-marker collection of synthetic E2E.
5. **Debt multiplier:** independent packaging paths require reconciliation for
   each future dependency, runtime or verifier change. Three similar changes
   would each touch both paths and need independent parity proof. The existing
   shared stager/materializer pass the deletion test: deleting them would spread
   admission and preparation complexity back into multiple callers.
6. **Options:** keep both builders (low immediate cost, continued drift); local
   refactor (small interface-neutral change, targeted regression coverage);
   replace deployment engine (large cost and lifecycle risk without evidence).
   Choose the local refactor. Native worker batching remains a separate option:
   recent shortcut fixes and receipt ordering justify excluding it here.
7. **Intervention:** retire the unused Preview builder; directly extract runtime
   using the same exclusions after complete archive validation; prove metadata
   and editable admission through one inventory; express the gate sequence once
   without rerunning synthetic. No new owner, cache, public schema or adapter.
   Completion requires targeted, architecture, unit and integration checks.
8. **Reversibility:** independent patches can be reverted. The old builder is
   retained in Git history, historical evidence and Preview wizard remain, and
   no installed files or persisted user state are migrated by this refactor.
9. **Decision record:** deepen existing modules by absorbing repeated discovery
   and staging work behind unchanged public interfaces. This improves locality
   and leverage without replacing valid seams. ADR-0017 and ADR-0020 remain
   authoritative. Review when a second builder, cached eligibility, runtime
   profile or new deployment lifecycle is proposed.
10. **Uncertainty:** eliminating a full runtime copy, a full metadata-tree scan
    and one pytest launch is measurable work reduction, not a measured end-to-end
    release speedup. This checkout's tests do not prove new compiled Setup bytes,
    clean-VM/browser trust, a GitHub runner cycle or an official downloaded update.
    Run the existing candidate workflow at the eventual release commit for those
    artifact-specific proofs.

## Local validation

- Targeted packaging, eligibility, harness, workflow and managed architecture
  checks: 81 passed before adding the final architecture safeguard.
- Pinned runtime parity: SHA-256
  `7c45c9622400d578709a9b2cddbe8124cc21d382409d9f13406d706d28e31b14`;
  all 2,295 file hashes and 120 directories match the baseline extraction/copy.
  The resulting Python 3.12.14 imports `venv`, `ensurepip`, `tkinter` and `ctypes`
  under isolated mode. Scratch receipt:
  `.clipai-test-artifacts/runtime-parity-408f663bc28b440aae52f7af933db2a2/parity.json`.
- One local staging comparison: baseline 8.82 seconds, direct extraction 5.20
  seconds. Order/cache/device effects are uncontrolled; this is neither a latency
  baseline nor a full release benchmark.
- The sandbox run stalled in Windows asyncio `_fallback_socketpair` before any
  changed runtime code, and OpenSSH could not write its fixture public key.
  Those runs did not pass. The approved run outside that restriction completed
  `scripts/verify_managed_update.py --stage managed-bundle` with exit code 0:
  2,040 unit/architecture tests passed (65 integration tests deselected), then
  2 loopback HTTP/signature tests and 2 real offline bundle tests passed. The
  latter covers initial installation, identity-bound health, the transaction
  fault matrix, rollback, retained old versions and unchanged shared data.
- Implementation/tooling net reduction: 183 lines across the two platform
  modules, staged harness and retired Preview builder. Contracts and regression
  tests were added separately. `git diff --check` passed.
