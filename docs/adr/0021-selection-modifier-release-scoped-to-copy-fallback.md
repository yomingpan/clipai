# ADR-0021: Selection modifier-release scoped to copy fallback

Status: accepted, 2026-10-11. Amends ADR-0016's modifier-gate ordering.

Read-only UIA captures the source bound at intent admission while physical
modifiers remain held. Modifier release protects only positively authorized
compatibility Copy. This preserves the user's selected input while preventing
synthetic Ctrl+C during a held gesture; Entry Panel must expose modifier failure
instead of silently substituting frozen clipboard input.

## Context and observed evidence

ADR-0016 gated before source validation and UIA. That coupled a harmless read to
Copy safety and allowed Entry's general unknown fallback to hide modifier failure.
The new policy oracle was made red before production changed. Measurements below
come from committed JSONL; the old gate's sleep latency is simulation overhead,
not device latency. Scenario fixture distributions differ, so exact-case counts
are not a before/after selection-quality metric.

| Evidence | Result |
| --- | --- |
| [Baseline gate](../../artifacts/selection-baseline-20261011.jsonl) | Seeds 17/41/73 each policy 480/480; expected exact 110/127/109 all available; p95 15.416–15.646 ms from real polling sleep |
| [Expected-red oracle](../../artifacts/selection-policy-expected-red.jsonl) | Updated 27-scenario policy against old ordering: 457/463/457 correct out of 480 |
| [Final virtual-clock gate](../../artifacts/selection-policy-attended-final-20261011.jsonl) | 27 scenarios; seeds 17/41/73, 480 cases each, three iterations; policy/exact rate 1.0, exact 109/112/109; six violations zero; deterministic; p95 0.042–0.051 ms |
| [Auto run 1](../../artifacts/selection-desktop-auto-20261011-3.jsonl), [run 2](../../artifacts/selection-desktop-auto-20261011-4.jsonl), [run 3](../../artifacts/selection-desktop-auto-20261011-5.jsonl) | Independent device runs, each 100/100; held 20/20 selected and clipboard 100/100 preserved per run; p50 23.519–24.750 ms, p95 41.574–44.472 ms |
| [Final auto regression](../../artifacts/selection-desktop-auto-attended-regression-20261011.jsonl) | 100/100; p50 29.917 ms, p95 49.984 ms; clipboard preserved, unknown_as_none zero |
| [Physical attended run](../../artifacts/selection-desktop-attended-run3-20261011.jsonl) | Four states × five rounds, 20/20; held_after_open 5/5 selected; no_capture_logged zero; clipboard 20/20 preserved; capture-log p50 31 ms, p95 47 ms |
| [Branch loop](../../artifacts/branch-loop.jsonl), S6-attended | targeted 421, architecture 62, unit 2142 all passed; successful baseline unit 2055 |
| [Native UIA smoke](../../artifacts/selection-integration-final-20261011.jsonl) | One integration case passed on the interactive Windows desktop |

The device timings cover capture, excluding host setup and the operator's hold
and acknowledgement. Attended observes the main application's content-free log;
it does not read selected text back for a content comparison. It verifies this
owned RichTextBox, not every application/provider/permission level.

## Decision and ownership

`SelectionCaptureCoordinator` remains the sole owner of capture ordering and the
modifier gate. The fixed flow is:

0. Already cancelled → cancelled.
1. Missing bound source → source_unavailable.
2. Source-current #1 failure → source_changed without probe.
3. Probe the bound source; no modifier polling before or during UIA.
4. Post-probe cancellation → cancelled; a cancelled probe terminates capture.
5. On focus_restored, recapture the original window; missing/different HWND or PID → source_changed, strategy uia; otherwise rebase.
6. Source-current #2 failure → source_changed, strategy uia.
7. Only unknown plus selection_detected or copy_selection_only waits for ctrl/alt/shift release. Timeout → modifier_timeout; cancellation → cancelled; both zero Copy and clipboard writes. The default deadline remains one second.
8. Source-current #3 failure → source_changed, strategy uia, no Copy.
9. Authorized Copy uses the single ClipboardTransactionCoordinator with source-current callback; otherwise return the UIA outcome.
10. Any exception → capture_failed; finally retain the existing content-free capture log format.

Core owns reason wire values, guidance categories and outcome classification.
Services alone derive Entry's automatic frozen-clipboard choice and speech
problem/advice. Modifier failure stays failed/retryable with explicit
UseEntryPanelClipboard available; other unknown plus frozen input retains Entry's
existing fallback. App/UI never compare reason strings or duplicate reason sets.

WindowsSelectionProbe detaches a retired worker before cleanup; failed retirement
retains shutdown ownership while allowing a new reusable worker. Stop still
reports unconfirmed exit, and responses interrupted by retirement/cancellation
are cancelled. RenderedContent owns the immutable, Tk-free content projection;
read-only semantic content comes from it, with live Voice Draft editing as the
explicit widget-reading exception.

## Alternatives and consequences

- Increasing the modifier timeout only moves the failure boundary and delays
  supported UIA reads. The release deadline stays unchanged.
- Waiting for Alt-up would delay reading the selected source and require another
  cross-layer event channel. Existing typed intents and bound capture identity
  remain sufficient.
- Blind Copy or generic unknown-to-none conversion would allow whole-line Copy
  and incorrect clipboard substitution. Positive capability evidence and
  repeated source checks remain mandatory.

The desktop evidence tool uses actual foreground activation before setting test
selection; otherwise WinForms can expose a stale initial UIA caret range despite
a native selection. Its operator acknowledgement completes key release/Esc before
changing a scenario. This setup correction is confined to the owned evidence
host; it changes no production focus or capture policy. Auto injects only adapter
modifier state; attended uses physical keys, never synthetic hotkeys.

## Safeguards and review triggers

AST tests close the emitted reason vocabulary, reject consumer string comparisons
and preserve Tk-free canonical ownership. The virtual-clock gate checks policy,
clipboard_dirty, unknown_as_none, blind_copy, copy_while_held and text_mismatch;
the all-none mutation must fail. Source/order/cancellation rejection tests and
worker identity tests prevent an unsafe happy-path-only regression.

Review on any wrong-source text, automatic clipboard use after modifier failure,
UIA held-gesture regression, renewed real-clock gate sleep, retained-worker
accumulation or unconfirmed shutdown, guidance category drift, display hints in
canonical output, or provider/control changes that invalidate the device evidence.
Recollect attended evidence when hotkey dispatch or Panel lifecycle changes.
