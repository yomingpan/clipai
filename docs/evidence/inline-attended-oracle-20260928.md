# Inline attended verdict diagnosis (2026-09-28)

## Judgment

**Yellow; local refactor, high confidence.** The attended assessor conflated a
requested action with its settlement and treated Escape propagation to the
external target as proof that ClipAI received Escape. Keep the existing single
assessor and correct its evidence rules; no new lifecycle owner is needed.

## Evidence and protected behavior

- Two Minimal cancellation runs ended with one `discarded` terminal, no Paste,
  unchanged target and clipboard, and a ClipAI hotkey receipt before discard.
  The target correctly received no Escape. Both original reports were blocked
  solely because `escape_input` demanded a target Escape event.
- One fixed-audio Minimal long-stop run had a target Paste and terminal receipt,
  but `refine_settled=failed`. The provider returned HTTP 503, then the user
  explicitly chose raw Paste from recovery. Its original `refine` report passed
  because the assessor checked `refine_requested` only.
- Preserve Escape suppression while Inline is active, explicit raw recovery
  after provider failure, operation identity, and independent target readback.

## Four-part diagnosis

1. **Owner:** `scripts/run_inline_controlled_desktop.py::assess` owns the
   attended verdict. `VoiceInputController` and Provider/Paste owners retain
   product state; the assessor only interprets their evidence.
2. **Capability:** This is one reusable scenario oracle, not a special
   exemption for either run. It must distinguish input receipt, suppression,
   requested refinement, and settled refinement.
3. **Boundary:** The old oracle used target keyboard delivery as evidence of
   ClipAI's Esc intent and treated an app request as evidence of provider work.
4. **Enforcement:** Focused negative tests require an App hotkey receipt in
   order, zero target Escape events, and `refine_settled=completed` before a
   successful refine verdict. The complete validation runner includes these
   tests.

## Debt, options, and decision

The multiplier was an unstable evidence contract: three more similar cases
would keep turning correct suppression or recovery into misleading verdicts.
Keeping the old rule is cheap but preserves that risk. Building a second
assessor duplicates ownership. **Decision:** adjust this assessor and retain
the original reports unchanged. Store content-free hotkey receipt lines with
Inline trace evidence in new runs; older runs without such evidence remain
blocked unless their same-session App log can supply it. This is reversible by
reverting the assessor and its tests, with no product-state migration.

## Completion and uncertainty

The two saved cancellations re-assess to pass from their original target events
and allowlisted same-session App log. The saved refine run re-assesses to fail
for refinement success while its target readback and explicit recovery remain
pass. The verified reports sit beside the originals under `artifacts/`.
Hotkey receipt is still App-side evidence, not an independent HID observer.
Review this boundary when a dedicated physical keyboard observer is available.
