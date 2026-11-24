# Alt shortcut stale punctuation diagnosis (2026-10-26)

## Judgment and evidence

Yellow: use a bounded local correction inside the platform keyboard adapter.
Confidence is high in the reproduced defect, moderate that it explains every
post-export physical-key attempt: the export contains no raw events for those
attempts. No production changes were made during this diagnosis.

The supplied diagnostics show `Escape press ignored as chord` with
`pressed=[':', '<', '?']` at 16:49:10. The final Inline interaction settled
recognition, refinement, Paste dispatch and clipboard restoration at 22:54:08.
No subsequent capture is recorded. These are facts; a stopped hook remains an
alternative explanation for later attempts.

`python -m pytest tests/platform/test_right_alt_hotkey.py -k typing_shifted -q`
fails all three punctuation replays before the fix. A key-down `:` and key-up
`;` carry the same Windows VK but normalize to different retained tokens.
The remaining token prevents both Right Alt solo admission and exact Left Alt
Panel admission. No lost hook event, live provider or microphone is required.

## Protected capability and four-part diagnosis

Preserve solo Right Alt release intent, the 500 ms threshold, chord rejection,
Left Alt Panel admission, injected-event exclusion and real held-key protection.

1. Owner: `_HotkeyDispatcher` remains the single pressed-state owner.
2. Capability: stable physical-key normalization and stale-state polling are
   reusable keyboard-adapter capabilities, not punctuation-specific UI recovery.
3. Propagation: character translation leaked into physical hold identity inside
   platform. No service/UI boundary needs changing.
4. Enforcement: replay shifted/unshifted releases with unchanged VK, recover a
   missed release using physical polling, and retain rejection while the same
   punctuation key is genuinely held. Run with Right Alt configured, since the
   older unbound-character regression test omitted this production binding.

## Debt multiplier and options

Tracking all ordinary keys for solo chord rejection exposed a gap in the prior
unbound-character protection. Three more character/layout cases would otherwise
invite three reset exceptions. Ignore all ordinary keys: cheap and reversible,
but permits solo intents during real held keys. Reset state in runtime/UI: adds
a second owner and unrelated lifecycle coupling. Recommended: normalize Windows
OEM punctuation by VK and query that same token in the existing state reader;
small, reversible and confined to platform.

## Intervention, sequence and decision

First retain the failing replay; then share OEM VK/token metadata between
normalization and physical polling; add missed-release and genuinely-held cases;
update the listener contract; run keyboard, architecture, unit and Tk smoke
checks. Exclude provider, voice state, clipboard, hook restart and UI workarounds.
Completion means both Alt entries work after the replay, without admitting a
solo shortcut while another key remains held.

ADR: physical Windows punctuation identity uses VK before translated character;
the existing dispatcher and physical reader share its mapping. Alternatives are
blanket resets or dropping chord protection. Consequence: configurable OEM
bindings use stable unshifted tokens, like existing letter/digit/grave behavior.
Review on another layout-dependent mismatch, new retained unqueryable token,
or reproducible hook loss. A physical-key retest in the affected application
remains the highest-value evidence beyond deterministic adapter tests.

## Validation

- Before correction: three original `:`, `<`, `?` replay cases failed.
- After correction: 214 targeted keyboard/runtime cases passed, including the
  expanded OEM replay matrix and real state-reader seam with controlled Win32
  responses for held versus missed-release cases.
- Architecture: 65 passed. Real Tk Pill integration smoke: 14 passed.
- Full default suite: 2473 passed, 69 integration cases deselected (91.65 s).
  Used a workspace-local `CLIPAI_TEST_TEMP_ROOT` after sandbox temporary-path
  access failed. Full-suite execution required leaving the restricted sandbox:
  its local socket restriction blocked Python asyncio socket-pair creation in
  unrelated runtime composition tests. No production workaround was added.
- `git diff --check` passed. No physical keyboard retest or running-application
  restart was performed; the source correction takes effect after the fixed
  checkout is loaded by the application.
