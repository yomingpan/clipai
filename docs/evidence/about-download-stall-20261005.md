# About download stall: diagnosis and repair

1. **Judgment:** Yellow; recommend a local refactor of preparation lifecycle,
   with high confidence in the blocking stream mechanism. Preserve published
   acceptance assets and the installed application until a fresh candidate is ready.
2. **Evidence:** The attended acceptance helper's Python 3.12 worker stack is in
   `HTTPResponse.read -> _response_chunks -> atomic_write_verified_chunks`.
   Its main thread eventually joins that worker at interpreter shutdown. No
   handoff host/request was observed. A real gated loopback HTTP test fails:
   the first available byte cannot be obtained within 0.3 seconds because
   `read(1 MiB)` waits for the remainder. File length alone is not settlement
   evidence. Subsequent inspection found two distinct update transactions:
   `update-79011f2e4a0e4e1bb3e842f216aee948` completed its bundle at 22:07:47;
   `update-068d8ed412d943b2837e203287cfaf80` began at 22:08:14 and completed
   at 22:17:24. The earlier stack therefore belonged to the second download.
3. **Protected capability:** Explicit About intent selects an admitted HTTPS
   release, downloads exact catalog-bound bytes atomically, then hands off only
   after verification and matching external readiness. Preserve URL admission,
   signature/hash/size checks, immutable bundles, and user state/secrets.
4. **Diagnosis:** Runtime owns the About operation and projection; services owns
   discover/download coordination; transport owns blocking reads; the external
   host owns its transaction after handoff. Bounded preparation, cancellation,
   and stage reporting are reusable capabilities. Today the UI sees one undifferentiated
   pending state and the transport lacks the cancellation/whole-transfer contract.
   Enforce the boundary with operation-scoped typed progress, a shared cancellation
   token, and real streaming/timeout/atomic-cleanup tests.
5. **Multiplier:** Hidden blocking work and missing settlement. Three future
   retry, progress, or exit fixes would otherwise create separate timers or worker
   registries and multiply races around the same download.
6. **Options:** A UI timer is cheap but cannot settle the worker. A full HTTP
   migration is costly and unnecessary. Local streaming/deadline/token changes
   remove the demonstrated mechanism and remain independently reversible.
7. **Intervention:** One preparation context across existing ports; available-byte
   reads, a finite whole-transfer deadline, real stage notifications, cancellation
   before external handoff, and runtime teardown signalling. No new supervisor,
   provider transport, global queue, range downloader, or trust override.
   Completion means bounded failure/retry, cleanup without replacing known-good
   bytes, and typed UI state driven by the actual stages.
8. **Sequence:** Preserve the failing HTTP test; add deadline/cancellation and
   projection regressions; extend the existing preparation ports; run targeted,
   architecture, unit and real loopback gates; prepare fresh release evidence.
9. **ADR:** Keep current owners and introduce an explicit preparation lifecycle
   contract. Reject a display-only timeout and speculative network rewrite.
   Cancellation applies before host publication; the existing external host
   remains responsible for already published transactions. Review again if
   native tests show an IO call cannot settle within the documented socket bound.
10. **Uncertainty:** GitHub/CDN cause remains unproven. Repository tests do not
    certify an installed or published release.
    Highest-value next evidence is a fresh source-bound candidate performing the
    actual About update and exiting without a stranded worker.

## Installed-code replay and package-context path rejection

The first transaction's completed ZIP independently hashes to B's catalog-bound
`47f08a74912c5130a41c50dff22e3a5b298070856ee37078b30b7a83b6f7d2eb`.
An installed-A `-I` read-only replay, substituting already hashed bytes and
redirecting any request serialization to an agent-owned artifact directory,
fails before download at `require_contained`. No host was launched and no
installed data was mutated. Under this process context, the declared shared
root resolves to `%LOCALAPPDATA%/ClipAI Candidate`, but its existing transaction
resolves beneath `%LOCALAPPDATA%/Packages/OpenAI.Codex_2p2nqsd0c76g0/LocalCache/Local/ClipAI Candidate`.
This is consistent with inherited packaged-app filesystem virtualization. A
new transaction initially passed admission; after writing, its physical resolved
path no longer matched the admitted destination. Do not relax containment or
redirect real user state to a second root to accommodate this test context.

Both attended helper PIDs exited on their own. The installed pointer still
reports 3.7.8, revision zero; neither transaction contains a handoff request.
Fresh device acceptance must launch from ordinary Windows outside the Codex
package context and separately confirm physical install/shared paths.

## Repository validation

`.venv/Scripts/python.exe scripts/verify_managed_update.py --stage managed-bundle`
passed: 1,959 unit tests (including architecture), synthetic 1, real HTTP and
signature 2, signed managed-bundle transactions 2. The new gated streaming and
stalled-cancellation HTTP tests also passed separately (18 targeted tests).
These are local implementation gates; actual published A-to-B acceptance is failed/pending.

## Fresh source-bound local candidates

Two private candidate source refs freeze the repaired app and its tested removal
changes, with only static metadata versions differing. HEAD remains
`b3422eb04bcdbb58300642498322e5aa458d205c`; the normal index and unrelated `.tmp/`
remain unchanged. A is `a2afb79c204a0bc5ae5688e77141540e862e58cf` (3.7.10), B is
`06b44cae73dfa1126ea5ee2ef5d86f4544030ffa` (3.7.11).

The agent-owned `build_fixed_pair.py` invokes the existing acceptance-pair and
Setup builders, first to obtain repaired A from the admitted dependency wheels,
then to seal the final repaired A/B with one disposable authority. Each app
wheel is built offline; Setup consumes its existing bundle. Both pass source
comparison, signature admission, installed-wheel smoke, compiled extraction,
and asset verification. Intermediate and final private keys are removed by the
existing builder's `finally` cleanup. Final `pair.json` explicitly records
`about_update=pending`, `clean_vm=deferred_by_user`, and `release_ready=false`.

Final folder: `artifacts/installer-acceptance-pair-20261005/`.
Upload proposal: `artifacts/github-acceptance-20261005/` (20 files).
Logs: `artifacts/about-acceptance-20261005/build-A.log` and `build-B.log`.
Exact hashes and external action boundaries are in the
[reviewable publication proposal](../specs/github-acceptance-release-20261005.md).
No tags were pushed, no release created, and no installed app replaced.

The separate helper now reuses `require_contained` to inspect actual shared
and existing update paths before application construction. Its latest 14 unit
tests pass. An installed-interpreter read-only invocation in the failing
context rejects `managed-update/about-acceptance` with the ordinary Windows
PowerShell instruction before any UI, verification write, download or host.
Package identity alone was insufficient in this environment, so the guard
uses filesystem evidence. Actual standard-desktop acceptance remains pending.
