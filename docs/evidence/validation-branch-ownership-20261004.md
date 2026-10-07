# Validation branch ownership diagnosis

1. Judgment: Green; extend the current release workflow with a bounded branch
   trigger. High confidence in ownership; remote execution remains to be proved.
2. Evidence: `release.yml` accepts only `v*` tags, while the release contract
   prohibits pushing a tag merely to explore. The remote develop baseline is
   `a0502d3`; its green Windows CI does not cover `01bfb04` or Setup assembly.
3. Protect one app wheel, one hashed lock/wheelhouse, one signed managed bundle,
   one Setup consuming those exact bytes, existing verification and no publishing.
4. Ownership: workflow owns build composition/authority admission; existing
   managed and Setup builders retain their artifact responsibilities. Isolated
   validation is a reusable entry to the same build, not another release channel.
   Trust admission stays at composition; About and verification do not branch
   on CI mode. YAML tests enforce one payload build, tag-only official secrets,
   ephemeral branch authority, read-only permissions and unconditional cleanup.
5. Debt multiplier: copying a Preview pipeline for each CI/manual/test mode
   would multiply resolution, signing and packaging policy. Share the existing
   payload/build/verification steps and branch only at authority admission.
6. Options: push exploratory tags (breaks contract); duplicate workflow (drift);
   bounded branch trigger (small reversible change, requires remote evidence).
7. Recommendation: `release-validation/**` accepts isolated technical builds
   with a per-run Ed25519 key. Tags continue requiring the official configured
   authority. Neither path publishes or approves native distribution/signing.
8. Migration: add trigger/admission tests, run local architecture checks, commit
   the real B version 3.7.9, push only a new validation branch and inspect its
   actual jobs/artifacts. Do not move tags, main or remote develop.
9. ADR: keep one workflow and both existing builders. Per-run branch trust is
   discarded and cannot update earlier local candidates. A separately prepared
   A/B pair must share its own admitted public keyring. Review this seam if
   signing or build authority gets duplicated across workflows.
10. Limits: branch CI is remote Windows build evidence, not a clean VM, actual
    About click, publisher signature or new-user observation.

References: [GitHub push filters](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#push)
and [workflow triggering](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow).
