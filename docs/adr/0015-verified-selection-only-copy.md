# ADR-0015: Verified selection-only Copy for inaccessible card content

Status: accepted, 2026-09-06. Bounded amendment to ADR-0014's Copy admission rule.

## Judgment and evidence

Yellow: retain the selection owners and make a local adapter/contract extension.
High confidence for the tested Anki main card view; no claim about all editors.
The user requested restoration of Anki selection-to-speech after the first fix
only handled the exception. The 20260906-042155 diagnostics show three consecutive
`uia_unsupported` speech failures. Native inspection of the same Anki HWND/PID
showed Qt `MainWebView` content without TextPattern. A live pre-fix capture of the
user-prepared selection returned unknown/unsupported and zero characters.

[Anki's onCopy](https://github.com/ankitects/anki/blob/main/qt/aqt/webview.py)
dispatches QWebEnginePage.Copy.
[Qt's WebAction contract](https://doc.qt.io/qt-6/qwebenginepage.html#WebAction-enum)
defines Copy as copying the current selection, with inapplicable actions inert.
This provides a narrower capability than arbitrary synthetic Ctrl+C.

## Protected behavior and diagnosis

- SelectionCaptureCoordinator remains the single capture owner; InputResolver
  owns priority and ClipboardTransactionCoordinator owns mutation/restoration.
- This is a reusable selection-only Copy capability with one verified source
  profile, not a speech-specific Anki branch.
- Native process/framework/control knowledge stays in platform. Only an explicit
  boolean capability crosses core's immutable outcome contract into services.
- Tests enforce exact profile recognition, reject wrong processes/views/focus,
  preserve the capability through worker serialization, and prove selection
  reaches Speech while no-copy/timeout never speaks the old clipboard.

The debt multiplier was an incomplete capability contract: TextPattern absence
was conflated with absence of every safe selection retrieval method. Three more
consumer-specific workarounds would duplicate source policy and restoration.

## Options and decision

Keeping fail-closed rejection preserves isolation but breaks this core user flow.
Unconditional Ctrl+C is small but can read an unselected editor line. An Anki
add-on could expose selection directly but adds installation and lifecycle cost.
Choose the bounded native profile plus existing transaction. It is reversible by
removing one profile without changing runtime, UI, or clipboard ownership.

`copy_selection_only` is capability evidence, never fabricated positive selection
evidence and never proof of `none`. Only a successful, source-validated temporary
copy establishes selected text. Unknown, empty copy, timeout and cancellation
cannot fall back to the previous clipboard. No selection content is logged.

## Migration and verification

Add the typed capability, recognize the validated focused Anki card ancestry in
the existing disposable UIA worker, transport it unchanged, and admit existing
copy transactions from that capability. Keep all identity, cancellation, deadline
and conditional restoration checks. No second capture path or owner is created.

Live verification against the user's Anki main card returned selected/copy,
44 characters, exact expected-text match, and equal clipboard snapshots before
and after. Automated regression tests additionally cover no-copy and stale source.
With the user's explicit permission for Edge speech, the real SpeechCoordinator
also captured the same selection, verified the expected text before transmission,
and completed EdgeSpeechOutput playback with the clipboard snapshot unchanged.
The earlier Tk callback handling fix remains in place.

## Uncertainty and review trigger

Anki add-ons can change copy behavior; native class names are capability matching,
not a security boundary. The profile excludes other Anki windows until verified.
UIA process startup still adds latency. Revisit on any wrong-text capture,
Anki/Qt ancestry change, add-on copy override, or request for a second profile.
Measure real selected/no-selection behavior before broadening the profile.
Never infer `none` from a copy timeout or broaden matching to all Qt controls.
