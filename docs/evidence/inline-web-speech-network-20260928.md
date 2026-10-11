# Inline Web Speech network failure diagnosis

## Executive judgment

**Yellow; local refactor; high confidence in the error-reporting defect.** The production WebView page ignored a browser `network` recognition error. It then reported `ended` without a failure or transcript, allowing the controller's natural-end/no-speech path to mask a connection problem. The bounded repair routes that browser error through the existing typed `unavailable` failure and retry message.

## Triggering evidence

- The autonomous fixed-WAV host probe entered Listening and recorded microphone audio levels but no interim or final result in `zh-TW` and `en-US`. Audio level alone does not prove intelligible capture.
- A temporary copy of the production page emitted the otherwise hidden Web Speech error code `network` in `artifacts/inline-direct-webview-zhTW-errors-20260928.json`. The page source ignored `network` alongside `no-speech`; the existing test explicitly asserted that behavior.
- After the repair, the real WebView2 host emitted `failed` with `unavailable`, then `ended`, in `artifacts/inline-direct-webview-zhTW-network-fix-20260928.json`. It still produced no transcript. The specific external network/service cause is unverified.

## Protected capability

`no-speech` and natural ends may restart only while the same capture remains admitted. Explicit Stop and Cancel do not restart. The WebView host releases microphone tracks at terminal settlement; the transport maps browser events to typed voice events; `VoiceInputController` decides recovery and preserves finalized text. Inline network failure without text must not request Paste.

## Four-part diagnosis

1. **Owner:** The WebView host adapter owns translating browser error codes into transport events. `VoiceInputController` owns the resulting interaction decision; the UI only projects it.
2. **Capability:** A network failure is a reusable recognition transport failure, not an Inline-only exception. The existing `VoiceTransportFailure.UNAVAILABLE` and detail channel suffice.
3. **Boundary:** Browser-specific `network` knowledge stays in the adapter. No browser error string enters the controller or UI policy, and no second capture lifecycle is introduced.
4. **Safeguard:** A JavaScript simulation asserts `network → failed(unavailable) → ended` both during capture and after Stop, while network after Cancel preserves discard; service tests assert Inline recovery without Paste and visible failure reasons with partial text; the real WebView probe observes the typed failure and terminal pair. `no-speech` retains its distinct path.

## Debt multiplier and options

The debt multiplier was a hidden browser error combined with a test that only checked its omission. Three similar errors would make silence, service outage, and permission problems indistinguishable at the product boundary. Accepting the omission would preserve misleading feedback; a new error state owner would duplicate the controller; rebuilding the speech stack would be disproportionate. The chosen local mapping is reversible and uses existing ownership.

## Intervention and migration

The repair changes the WebView error mapping and carries the existing failure message into Inline recovery when finalized text exists. It does not retry automatically, alter Paste or clipboard ownership, or claim the transcript succeeded. The regression tests failed before the mapping and message changes and passed after them. The full non-integration suite passed 1785 tests, and the complete Inline component run passed 446 fast, 14 Tk, and 4 WebView2 tests. The Tk run used a workspace copy of the bundled Tcl/Tk data because direct reads from the runtime cache intermittently failed.

## Concise ADR and review trigger

**Decision:** Treat Web Speech `network` as an immediate typed recognition failure with a connection remedy; keep `no-speech` eligible for controller-directed natural-end recovery. **Alternative rejected:** silently ignore both and infer the reason from End. **Consequence:** an in-flight capture can terminate earlier on network failure while preserving any finalized content through the existing controller path. Review this mapping if WebView2 begins emitting recoverable network events without ending recognition, or if a successful fixed-audio cohort contradicts it.

## Remaining uncertainty

The probe used speaker-to-microphone acoustic replay on one PC, with no independent microphone recording or physical shortcut observer. It cannot establish which network dependency failed or a representative failure rate. The next useful evidence is a successful same-condition transcription on a connected desktop, followed by the full Choice and Minimal target matrix and first visible frame observation.
