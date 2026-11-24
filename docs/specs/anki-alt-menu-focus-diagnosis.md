# Anki Alt Entry Panel selection failure

## 1. Judgment

Initially Yellow; resolved by a local native shortcut change after the user
requested implementation. The real Anki regression failed without masking and
passed with masking before native Alt release. Focus deadlines and the Anki copy
profile are unchanged.

## 2. Evidence

- Commit `c438ecd` extends external-window readiness waiting. It does not preserve
  the source's virtual control focus across a bare Alt gesture.
- Supplied `clipai-diagnostics-20260908-000142/clipai.log` records seven
  `uia_unsupported` captures on Anki HWND `330da8`, PID `31976`, followed by a
  successful `selected / copy` capture. Window activation and confirmation succeed.
- User confirms Anki card front, mostly failing with intermittent success.
- Live read-only UIA sampling on 2026-09-08 (local time):
  - 08:07:23: `QObject / MainWebView / QWidget / AnkiQt`, all Qt; copy profile true.
  - 08:07:26: `QMenuBar / AnkiQt`; copy profile false.
  - HWND, PID and native focus HWND remain unchanged across that transition.
  - 08:07:54: returning to Anki still reports `QMenuBar / AnkiQt`.
- Matching application log: preparation `5e17e279f7984c7abdd75bb78b815b60`
  activates in 0 ms at 08:07:26.463, then returns `uia_unsupported` at 08:07:27.509.
  User independently confirms this attempt failed.
- Inference: the bare Alt interaction moves virtual focus to the Anki menu bar;
  checking only top-level foreground readiness cannot distinguish that state.
  Sampling does not establish whether key-down or key-up caused the transition.

## 3. Protected behavior

Read the user's selected card content through the existing verified copy path.
Preserve clipboard restoration, source validation, cancellation, and rejection of
unsupported sources. Normal Alt menu use, Alt+Tab, other Alt chords and injected
event filtering must remain correct.

## 4. Ownership and boundaries

- Capture identity/result: `SelectionCaptureCoordinator`; input priority:
  `InputResolver`; clipboard transactions: `ClipboardTransactionCoordinator`.
- Physical shortcut state: existing platform hotkey dispatcher/listener.
  External-window readiness: `SystemExternalWindowActivator`.
- The dispatcher now owns native release settlement on its existing hold record;
  the Windows event filter performs menu masking before forwarding the release.
  It does not create a second hold or capture registry.
- This is reusable shortcut/native-input behavior, not an Anki UI exception.
  Anki classes must stay in the existing platform copy profile, not runtime/UI.
- Enforce with shortcut delivery/state tests plus real Qt virtual-focus smoke
  coverage. A same-HWND assertion alone is insufficient.

## 5. Debt multiplier

Native virtual focus is hidden state absent from readiness tests. Three more
application-specific delays or blind copy exceptions would duplicate policy,
increase latency and expand wrong-content capture risk.

## 6. Options

| Option | Benefit | Cost / risk | Reversibility |
| --- | --- | --- | --- |
| Longer wait | Small diff | Menu focus may persist indefinitely | Easy |
| Broaden copy to menu ancestry | Small diff | No evidence Copy targets the selected card | Easy but unsafe |
| Local native shortcut intervention | Addresses gesture side effect | Requires validating normal Alt and chords | Bounded adapter change |
| Change entry gesture | Removes bare-Alt conflict | Changes user interaction | Config/product decision |

## 7. Recommended intervention

Implemented a local native shortcut intervention scoped to the existing claimed
modifier-hold identity. `keyboard_menu.mask_alt_menu` sends an unassigned VK_E8
down/up pair from the hook before physical Alt-up is forwarded. Injected events
remain excluded from intent processing. Native release is settled once, and a
release observed before the deadline invalidates a late timer. Failures are logged
without dropping the physical release. The SendInput function uses a separate DLL
wrapper so its typed INPUT signature cannot overwrite pynput's shared signature.

Completion requires repeated physical Alt holds preserving card virtual focus,
successful source-bound capture, unchanged clipboard after cleanup, and ordinary
short Alt/menu/Alt+Tab behavior. Cover release, cancellation and shutdown.

## 8. Reversible sequence

Reproduced the key-down/key-up transition against the user's prepared Anki card,
validated the isolated mask prototype, added native-hook regression tests, then
wired the existing listener. The disposable prototype is removed. Reverting the
native hook/mask changes leaves the existing source-bound selection contracts
intact. One listener and one capture path remain.

## 9. Decision

Context: foreground readiness does not imply selection-control readiness after a
bare modifier shortcut. Decision: keep native gesture side effects at
the platform shortcut boundary and retain strict selection evidence. Alternatives
are additional waiting or broader copy admission; neither addresses the observed
focus transition. Consequence: native gesture compatibility needs real integration
coverage. Review on any menu/chord regression or application with different Alt
semantics. No application-specific runtime branch is introduced.

## 10. Validation and uncertainty

Final validation: full unit suite 1333 passed (14 integration cases deselected),
architecture suite 39 passed, and the opt-in Anki integration test passed.

Pre-existing selection tests: 40 passed; they did not cover the gesture failure.
The live prototype failed with `Alt release moved selection focus to menu` and
passed when the single masking variable was enabled. The durable regression is
`tests/platform/test_anki_alt_menu_integration.py`: five holds preserve MainWebView
focus, and short Alt before and after still toggles QMenuBar. It exercises the
registered production listener with synthetic Alt admitted only in the test
process. Native hook tests additionally cover early release/late timer, repeated
events, generic/left/right Alt, injected events and injection failure.

After the fixed listener smoke, the existing SelectionCaptureCoordinator read
65 selected characters through `strategy=copy`; the full clipboard snapshots
before/after compared equal. No text was printed or sent to a provider.

The initial read-only probe emitted no text. Subsequent authorized regression
tests sent Alt and the menu mask; the separate selection smoke used the existing
restoring clipboard transaction. Physical-key end-to-end confirmation after
restarting the user's running ClipAI remains a release check; the isolated test
does not validate every Qt version, remapper or elevated target.
