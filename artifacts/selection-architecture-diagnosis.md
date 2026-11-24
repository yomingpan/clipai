# Selection capture diagnosis (before implementation)

Judgment: Yellow; choose a local refactor, with high confidence in ownership and
policy evidence. Device and physical-key behavior still requires measurement.

Observed at baseline commit 2f648d0: `SelectionCaptureCoordinator.capture` waits
for modifiers before validating/probing the bound source; Entry runtime applies
clipboard override to every unknown outcome; `_retire_owned` clears its pointer
only after potentially raising cleanup; `semantic_content` reads styled widget
text. These are mechanisms, not evidence that every Windows app is affected.
Recent base-dialog commits cover regeneration, selection and voice: unrelated
uses share the same content boundary. A second policy/content owner would
multiply fixes across all consumers.

Protected capability: bound HWND/PID and focus, confirmed-none versus unknown,
conditional clipboard restoration, explicit direct-action recovery, immutable
frozen input, operation-scoped cancellation, and worker shutdown accounting.

Ownership: core alone defines reason/guidance semantics; selection services own
capture order and Entry fallback policy; the clipboard coordinator owns all
temporary mutation; WindowsSelectionProbe owns worker membership and retirement;
RenderedContent owns read-only canonical content and selection/block projections.
These are reusable capabilities, not speech-, Anki- or Entry-specific native
branches. Native focus/copy trust stays in adapters. Only typed outcomes and
capabilities cross into services; widgets never classify reason strings.

Debt multiplier: hidden cleanup state, scattered string policy and reconstruction
from display content. Three similar future changes would otherwise repeat reason
lists, focus/cancellation handling and canonical normalization across consumers.

Options: retain current behavior (cheap but preserves the defect); local refactor
(bounded policy/model change with existing ports); migrate or rebuild (higher
cost and unnecessary boundary risk). Recommend exactly the local refactor.
Safeguards: AST checks for closed reason emissions/consumer string comparisons;
public capture order, cancellation and zero-mutation tests; failed-retirement
replacement tests; independent deterministic 27-scenario oracle and mutation
test; widget-independent canonical tests. No new event channel or clipboard owner.

Reversible sequence: baseline; reason classification; failed-worker detachment;
gate oracle red; capture/fallback policy green; runtime guidance; content model;
controlled desktop harness; actual-evidence documentation amendment. Each step
uses the branch loop; no new and old owners remain concurrently active.

Decision sketch: move modifier release to positively authorized Copy fallback;
detach an unhealthy owned worker before attempted retirement while retaining
failed cleanup in the lifecycle registry; store read-only content independently
of Tk. Alternatives are longer timeout and delayed Alt-up capture. Review on
wrong source, unknown direct fallback, orphan worker, duplicated reason policy,
or any read-only output rebuilt from widgets. Final ADR waits for device evidence.

Uncertainty: automatic desktop measurements do not validate physical hotkey
dispatch or user apps. Highest-value remaining evidence is controlled auto and
attended capture with preserved clipboard fingerprints and no recorded content.
