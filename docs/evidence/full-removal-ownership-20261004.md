# Full-removal ownership diagnosis

1. Judgment: Green; extend the existing uninstall policy locally. Confidence:
   high for ownership, device acceptance still required. No second engine/gate.
2. Evidence: `first_install_backend.start_maintenance_helper` previously copied
   a private runtime and abandoned the copy; retained-data naming also hid the
   newly requested data disposition. This is an observed cleanup ownership gap.
3. Protected behavior: default retained-data removal, broken-venv maintenance,
   native identity validation, busy rejection, exclusive installation gate.
4. Ownership: `UninstallCoordinator` owns explicit policy/result; filesystem
   backend owns bounded file mutation under the same gate; Windows integration
   owns shortcuts/registry; one OS supervisor owns the one temporary helper.
   Full removal is a reusable disposition of uninstall, not a new uninstaller.
   UI sends typed intent; it never deletes files. The safeguard is a fixed-root,
   ownership/reparse/other-install preflight and success only after settlement.
5. Debt multiplier: implementing each future removal mode in Setup separately
   would duplicate deletion authority and recovery rules three times. Passing
   one immutable intent through the current engine prevents that growth.
6. Options: leave cleanup pending (small cost, contradicts requested result);
   extend existing policy (bounded and testable); introduce separate uninstaller
   (more migration/risk, no demonstrated benefit).
7. Recommendation: one boolean disposition on renamed `UninstallIntent`, default
   false; same coordinator/backend, one post-exit supervisor. Exclude broad temp
   sweeps, OS history, shared prerequisite removal and user process termination.
8. Migration: rename retained-only surfaces after searching imports/tests/docs;
   retain defaults; add opt-in guards; wire both front ends; verify safety and
   real worker exit/cleanup. Old candidate EXEs retain their old behavior.
9. ADR: keep current engine and gate, generalize explicit removal policy. A
   full-data failure cannot roll back deleted data, so preserve owner evidence,
   report failure and offer same-Setup retry. Review if a future data location
   lies outside the dedicated root or multiple installations share live data.
10. Limits: neither unit proof nor fixture worker exit proves clean-VM actual
    full-app uninstall. Final changed Setup needs wheel/bundle rebuild and
    device acceptance; the earlier delivered hash contains neither change.
