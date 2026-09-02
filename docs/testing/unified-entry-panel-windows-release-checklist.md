# Unified Entry Panel Windows release checklist

This is a blocking release gate for the ADR-0013 migration. Unit tests are
necessary but cannot prove native keyboard coexistence, compositor continuity,
IME behavior or mixed-DPI placement.

## Test setup and evidence

- Use an interactive Windows desktop, not an RDP session unless RDP is itself a
  supported target.
- Record Windows version, keyboard layouts, ClipAI commit, monitor work areas
  and scaling. Include one 100% display and one display at 125%, 150% or 200%
  when mixed-DPI hardware is available.
- Run `scripts\run_unified_entry_release_gate.ps1` and retain its output.
- Run `.venv\Scripts\python.exe scripts\repro_popup_dpi.py`; every monitor must
  report `cached==truth=30/30`, `topmost=30/30` and `visible=30/30`.
- For continuity checks, run `scripts\app_flash_watch.py --help`, then sample
  the ClipAI process at 20 ms while performing the Panel-to-result transition.
  Retain the sampler output and a screen recording.

Any failed row blocks release. Record `PASS`, `FAIL` or `BLOCKED` and attach the
observed evidence; do not infer a pass from unit tests.

## Native Alt coexistence

Test both left and right Alt where the keyboard exposes them.

- Tap or hold Alt for 499 ms: no Panel, delayed flash or claimed key remains.
- Hold Alt through 500 ms: exactly one Panel appears. Auto-repeat and a second
  timer callback do not open another Panel.
- While holding Alt, press top-row `0`–`9` and numpad `0`–`9`: the matching
  Panel slot is invoked at most once. Repeat after releasing Alt with the Panel
  focused.
- Exercise every configured `Ctrl+Alt` shortcut with top-row and applicable
  numpad digits. Behavior and short/long press semantics remain unchanged.
- Verify native `Alt+Tab`, `Alt+Shift+Tab`, `Alt+F4`, `Alt+Space` and `Alt+Esc`.
  ClipAI must not open or claim a Panel gesture.
- Verify `Shift+Alt` and `Win+Alt` combinations used by the system or host app.
  They remain native and produce no delayed Panel.
- On an AltGr keyboard layout, type `@`, braces, backslash and the layout's
  other AltGr characters using both observed Ctrl/Alt event orders. No Panel or
  configured `Ctrl+Alt` Action is triggered.
- Alt-tab away while the 500 ms deadline is pending, release Alt outside
  ClipAI, return, and repeat. No stale callback may open a Panel.

## Frozen input and IME

- Select text in two different target applications, open the Panel, then change
  selection and clipboard before choosing an Action. Preview and execution use
  only the input captured when the Panel opened.
- Repeat with no selection and clipboard text, then with a clipboard image.
  Disabled reasons must match the selected Action's input mode.
- Force the original target to lose foreground during capture. One full retry
  is permitted; a second loss fails closed and offers Retry without reading a
  different foreground window.
- In a result Popup, select a substring and invoke Chain. It uses that selection;
  with no selection it uses the complete displayed canonical content. Workflow
  identity and parent-step lineage remain unchanged.
- Use Microsoft Bopomofo or another CJK IME in More search and any editable
  result field. Composition, candidate selection, Enter and Esc behave normally;
  digits committed by the IME are not mistaken for global Alt-held selection.
- While external input is preparing, navigate root → scene → More and toggle
  density. Capable cards show neutral loading without red/disabled styling and
  cannot invoke; genuinely blocked cards keep their authoritative red reason.
  Opening and settlement produce no body flicker or card replacement.
- On scene and More, use both the left Back control and `Ctrl+Z`; verify the
  same lifecycle, source preview, density and preparation state remain. At root
  Back is a no-op. Press Esc on each page and verify immediate close plus
  preparation cancellation; the right header text always remains `Esc 關閉`.

## One primary surface and visual continuity

- Open the Panel from an external application and admit an Action. The native
  window handle remains the same from Panel through first result projection.
- Open the Panel over an existing result. Its outer x/y/width/height remain
  exact. Esc restores the prior result including selection, scroll, feedback
  overlay and operation state.
- Admit Chain from that Panel. Result content replaces Panel content in the
  same native window; no second `PopupControl`, Tk root or mainloop appears.
- During each transition, 20 ms sampling reports exactly one visible ClipAI
  primary window, with no zero-window gap, second visible primary window,
  blank/opaque intermediate frame or taskbar/Alt+Tab entry.
- Repeat with provider busy and Voice starting/listening/finalizing. Provider
  busy shows authoritative disabled reasons; Voice phases reject Panel opening
  without hiding truthful Voice feedback.

## DPI, multiple monitors and overflow

- Repeat external Panel, existing-result Panel, Esc restore and accepted
  replacement on every monitor and across a mixed-DPI pair.
- Drag the result to a new position, open the Panel and admit an Action. Physical
  position and toolkit-logical size remain exact through both replacements.
- Drag the same primary surface across a DPI boundary, close it, and open a new
  lifecycle on each monitor. Text, icons, hit targets and rounded edges are
  correctly scaled once—never clipped or double-scaled.
- Toggle compact/detailed density and open More with enough candidates to
  overflow. Only the mounted content scrolls; the outer window neither grows,
  jumps monitor nor changes dimensions.
- Test work-area edges, negative monitor coordinates, taskbar on each edge and
  cursor-near-corner placement. The host remains inside the selected work area.

## Exit criteria

Release is allowed only when the automated gate is green and every applicable
manual row above is `PASS`. A missing mixed-DPI monitor may be recorded as
`BLOCKED`, but the release remains blocked until equivalent physical hardware
evidence is attached.
