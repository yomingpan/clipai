# ADR-0013: Unified Entry uses one primary surface and input frozen at open

## Status

Accepted — implemented.

The migration landed incrementally: complete Alt coexistence, typed frozen
input, open-time preparation, `PrimarySurfaceHost`, same-shell Entry/result
replacement, centralized geometry/DPI/drag, Windows release gates, and removal
of the legacy two-window handoff path.

This ADR partially supersedes ADR-0012. It preserves ADR-0012's semantic
ownership boundaries but replaces two decisions:

1. Entry Panel and the resulting Popup no longer use two independently visible
   top-level windows joined by a hide/reveal handoff.
2. External input is prepared when the Panel opens, not after the user chooses
   an Action.

## Executive judgment

**Classification:** Yellow.

**Primary recommendation:** incremental migration.

**Confidence:** high for the ownership and input decisions; medium for the
final Windows focus/DPI mechanics until measured on real multi-monitor systems.

The existing bounded Entry Panel slice has healthy semantic owners, but its
native-window and input-timing contracts do not match the clarified product
requirements. Adding another handoff workaround would compound focus, DPI and
late-completion state. The smallest safe intervention is a single deep UI host
behind the existing Panel and Workflow interfaces, plus one identity-scoped
prepared-input capability behind the existing input seam.

No production code is changed by this ADR.

## Context and triggering evidence

### Verified facts

- `clipai/platform/hotkey.py` already models exact-Alt hold identity, a 500 ms
  deadline, Alt auto-repeat suppression, Panel digit claim, stale-state recovery
  and lifecycle settlement. It uses a passive `pynput` listener and does not
  suppress native Windows key delivery.
- `tests/platform/test_entry_panel_hotkey.py` covers Ctrl/Alt coexistence,
  top-row and numpad digits, early release, stale callbacks, auto-repeat,
  missing release and shutdown. It does not yet provide the full Windows Alt
  conflict matrix required below.
- `clipai/ui/unified_entry_panel.py` constructs its own `CTkToplevel`.
  `clipai/ui/base_dialog.py` constructs a separate result `CTkToplevel`.
  Therefore the present Panel-to-Popup transition uses two native windows even
  though both share one Tk root.
- `clipai/ui/entry_panel_handoff.py` correctly concentrates the current
  two-window prepare/commit/rollback protocol, but that protocol cannot prove
  that one visible window shell persists through the transition.
- Panel and Popup share `PopupLayoutPolicy`, logical `PopupBounds` and injected
  display metrics. However, result Popup construction calls the
  CustomTkinter per-window DPI resample in `clipai/ui/base_dialog.py`, while
  `UnifiedEntryPanelDialog` does not. Shared size calculation is therefore not
  the same as a shared DPI lifecycle.
- `EntryPanelRuntimeModule.open()` currently freezes either a Workflow identity
  or an opaque external-window reference. It invokes `InputResolver` only after
  Action selection, so the actual content is not frozen when the Panel opens.
- `InputTargetResolver` already implements the correct Chain priority:
  explicit Popup selection, otherwise the complete canonical displayed result.
  The resulting `InputDocument` retains Workflow and step lineage, and
  `WorkflowRuntimeModule.start_action()` validates that lineage before reusing
  the Workflow.
- Most configured Actions use `selection_or_clipboard`; the OCR Action uses
  `clipboard_image`. One preloaded text value is therefore insufficient for all
  Panel candidates.
- On 2026-09-01, the targeted Hotkey, Panel, runtime, handoff and base-dialog
  suite passed: 165 passed and 1 integration test was deselected. These tests
  protect current behavior but do not prove same-window continuity or real
  per-monitor DPI behavior.

### Inference

- The current two-window handoff can be visually acceptable on some systems,
  but Windows compositor timing, focus transfer and per-window DPI state leave
  a real gap between “same bounds in one UI turn” and “the same visible window.”
- Capturing content only after Action selection increases exposure to focus
  drift because the Panel has already become foreground. Freezing input at open
  removes that ambiguity at the cost of a visible preparation phase and a
  short-lived in-memory input bundle.

## Current capability and protected behavior

The migration must preserve all of the following:

- one `AppRuntime`, one Tk root and one mainloop;
- one visible primary ClipAI surface;
- existing `Ctrl+Alt+...` direct shortcuts and their short/long behavior;
- exact Alt-only 500 ms activation without intercepting native Windows Alt
  combinations;
- number selection both while Alt remains held and after Alt is released;
- `EntryPanelCoordinator` as the pure owner of navigation, search, density,
  candidate projection and numeric resolution;
- `EntryPanelRuntimeModule` as the owner of Panel membership and preparation
  identity;
- `WorkflowRuntimeModule.start_action()` as the only Action-admission seam;
- `WorkflowController` as the sole Workflow state owner;
- `PopupControl` as the sole per-Workflow Popup-actuation owner;
- one container-scoped `ClipboardTransactionCoordinator` for selection and
  clipboard transactions;
- Popup Chain priority and Workflow/step lineage;
- truthful pending, disabled, success, failure and cancellation feedback;
- no persistence or logging of selected text, clipboard content, images or
  Popup content;
- recent-action and Action Language Pack behavior defined by ADR-0012.

## Four-part architecture diagnosis

### 1. Single owners

| State or rule | Single owner |
| --- | --- |
| Physical Alt state, hold deadline and claimed digits | platform hotkey module |
| Panel navigation and candidate projection | `EntryPanelCoordinator` |
| Panel lifecycle and input-preparation identity | `EntryPanelRuntimeModule` |
| Prepared input resolution and mode compatibility | deepened input-resolution module in `services` |
| Temporary clipboard mutation/restoration | container `ClipboardTransactionCoordinator` |
| Native primary surface, bounds, DPI resample and mounted-view transition | new UI-internal `PrimarySurfaceHost` deep module |
| Workflow admission and visible Workflow membership | `WorkflowRuntimeModule` |
| Workflow execution state and accepted steps | `WorkflowController` |
| Result Popup actuation | `PopupControl` |

`PrimarySurfaceHost` owns toolkit/native shell mechanics only. It must not own
Panel navigation, Workflow state, Action admission, provider state or output
operations. Mounting the Panel in the same shell must not merge it into
`PopupControl`.

### 2. Reusable capability versus special exception

The reusable capability is a **single primary surface host** that can mount one
typed view at a time while preserving shell identity, bounds and DPI behavior.
It is not an Entry-Panel-specific flag inside `BaseDialog`.

The reusable input capability is an **immutable prepared input set** that can
resolve a frozen document for a known `InputMode`. It is not a special raw
dictionary stored by the Panel and not a second clipboard owner.

### 3. Knowledge crossing the wrong seams

The current design leaks two facts across seams:

- `ResultDialogPresenter` and `EntryPanelPopupHandoff` must know how two native
  windows hide, reveal, roll back and copy bounds. Those mechanics belong inside
  the one native surface host.
- `EntryPanelRuntimeModule` must wait for an Action definition before asking
  `InputResolver` for one document. After the product decision to freeze input
  at open, runtime should carry an immutable prepared set and ask it for the
  compatible document at admission time; it should not re-read external state.

### 4. Enforceable safeguards

- Typed identities distinguish Alt hold, Panel lifecycle, preparation,
  mounted-surface lease, Workflow, invocation and step.
- Architecture tests prohibit a second primary top-level window owner, a second
  clipboard transaction coordinator, UI imports of platform details and Panel
  calls to `PopupControl` or Action execution.
- Interface tests verify `PrimarySurfaceHost` through observable mount,
  replace, rollback, bounds and close outcomes rather than internal widgets.
- Runtime tests prove that only a matching Panel and preparation identity can
  publish preview data or admit an Action.
- Windows smoke tests prove native Alt coexistence, one-window continuity and
  real DPI behavior.
- The old and new surface paths may coexist only behind a short-lived migration
  flag. The old `EntryPanelPopupHandoff` path must be removed when the new host
  becomes the default.

## Debt multiplier

The multiplier is **duplicated native-window lifecycle plus unstable input
timing**.

If three similar features were added without this intervention, each would
need its own focus hold, per-window DPI initialization, bounds transfer,
hide/reveal rollback, dead-view cleanup and late input rejection. The result
would be three independent race matrices and multiple plausible owners for
“the visible ClipAI window.” Bugs would appear as intermittent flashing,
wrong-monitor scaling, stale content or a completion applied to the wrong
surface rather than as deterministic contract failures.

## Decision

### 1. Alt activation and coexistence

- Exact Alt alone held for 500 ms emits `OpenUnifiedEntryPanel` for one hold
  identity.
- Releasing Alt or pressing any other key before the deadline cancels only the
  Panel candidate.
- The listener remains passive. It does not suppress, replay or reinterpret
  Alt+Tab, Alt+F4, Alt+Space, Alt+Esc, AltGr, Shift+Alt, Win+Alt or configured
  Ctrl+Alt shortcuts.
- Once the Panel is open, top-row and numpad digits work while Alt is still
  held through the global digit claim. After Alt release, the focused Panel
  handles the same digits locally.
- A repeated complete Alt hold raises the existing Panel and preserves its
  prepared input; it does not recapture.

### 2. One primary visible window

Introduce a UI-internal `PrimarySurfaceHost` deep module. Its interface exposes
only lifecycle-scoped shell operations: acquire/show, mount, identity-matched
replace, restore, current bounds and close. The implementation owns:

- the one `CTkToplevel` used by an Entry Panel and its resulting Popup;
- physical screen position and toolkit-logical dimensions;
- per-monitor CustomTkinter DPI resampling;
- native task-switcher/topmost/activation mechanics through the injected
  `NativeWindowSurface` adapter;
- the mounted content slot and atomic replacement in one UI turn;
- rollback to the previous mounted view when replacement cannot complete.

The same top-level window is retained for one visible lifecycle:

```text
external source
  -> create host + mount Entry view
  -> Action admitted + result view built off-slot
  -> atomically replace Entry view with result view in the same host
  -> close result -> destroy host

existing result Popup
  -> retain host and result view state
  -> mount Entry view in the same host
  -> Esc/error -> restore prior result view
  -> Action admitted -> replace with the updated result view
```

The requirement is user-visible continuity, not a process-lifetime global
window handle. A later Alt gesture may create a new host after the previous
visible lifecycle has closed.

### 3. Input is frozen when the Panel opens

`OpenUnifiedEntryPanel` is the explicit typed intent that authorizes preparation
for this Panel lifecycle. Opening performs the following in order:

1. Capture the semantic foreground Workflow identity or exact opaque external
   window reference before the Panel takes focus.
2. Allocate a new preparation identity.
3. Mount the Panel immediately with a truthful `preparing` projection and
   temporarily disabled candidates.
4. Prepare input on interactive worker capacity; never on the UI or provider
   event loop.
5. Publish completion only through the typed command queue with both Panel and
   preparation identities.
6. Freeze the resulting `PreparedEntryInput` for the lifetime of that Panel.

For a Workflow source, preparation synchronously freezes explicit semantic
selection or, when none exists, the complete canonical displayed result. It
also freezes `workflow_id + step_id` for later lineage validation. It never
reads the external clipboard.

For an external source, preparation waits for Alt release, restores and
validates the exact captured target, and uses the existing selection and
clipboard seams. It prepares every currently supported compatible document
from one bounded capture attempt, including selection/clipboard text behavior
and clipboard image behavior required by OCR. It confirms that the original
target still owns foreground after capture. A focus loss retries the complete
operation once; a second loss fails closed.

`PreparedEntryInput` is an immutable typed model, not a raw dictionary. It
answers whether a document is available for an `InputMode` and returns the
already frozen `InputDocument`. Action selection never activates a window,
captures selection or rereads clipboard.

The bundle is memory-only and is cleared on Panel close, replacement, accepted
admission or application shutdown. It is never persisted, included in recent
history or written to diagnostics.

### 4. Source preview and failure behavior

The Panel always reserves one compact source-preview row in detailed and
compact density. Preparing, success and failure reflect the real preparation
lifecycle. Examples include:

- `正在讀取選取內容…`
- `選取文字：This is the captured input…`
- `剪貼簿文字：……`
- `剪貼簿截圖`
- `目前結果：……`
- `讀取失敗：原視窗已失去焦點`

Text is whitespace-normalized, limited to approximately 90 characters and
never expandable into a second content viewer. Image preview reports only its
source/availability, not raw encoded data.

Failure keeps the Panel visible and provides an explicit retry intent. Retry
allocates a new preparation identity but targets the same originally captured
source. It cannot substitute the current foreground window. To select another
source, the user closes the Panel, focuses that source and opens a new Panel.

Candidates remain visible. Each is enabled only when both authoritative runtime
availability and a compatible frozen input are present; otherwise it carries a
specific disabled reason.

### 5. Chain and concurrent operation behavior

- Chain input priority is explicit Popup selection, then complete canonical
  content of the currently displayed step.
- The new Action stays in the same Workflow and retains the captured parent
  step. Workflow runtime validates the lineage at admission and never replaces
  it with whichever Workflow later becomes foreground.
- While a provider invocation is active, the Panel may open and freeze input,
  but Actions remain disabled with the authoritative provider-busy reason. No
  Action is queued. When the provider settles, availability refreshes without
  replacing the frozen input or navigation state.
- During Voice starting, listening, stop-requested or finalizing, the Panel does
  not open. The Voice Popup remains visible so Listening, Stop and Finalizing
  feedback remains truthful and operable. A clear rejection message explains
  that Voice must finish or be cancelled first.

### 6. Size, DPI and overflow

- Entry and result views use the exact same outer logical bounds and physical
  screen position because the shell does not change.
- The host uses the same `PopupLayoutPolicy`, display metrics and DPI resample
  lifecycle for both views. DPI is applied exactly once to logical geometry.
- A content-density change never resizes or moves the outer window.
- Overflow scrolls inside the mounted view. It cannot grow the host into a side
  panel or move it to another monitor.
- User drag updates the host bounds once. Later projections and the
  Entry-to-result replacement preserve those actual bounds.

## Realistic alternatives

| Option | Benefit | Cost and risk | Reversibility | Decision |
| --- | --- | --- | --- | --- |
| Keep ADR-0012's two-window handoff | Smallest code change; current tests pass | Does not meet literal same-window continuity; duplicates DPI lifecycle and retains compositor/focus races | High | Rejected |
| Add more retry/delay logic to `EntryPanelPopupHandoff` | May reduce flashing on one machine | Treats timing symptoms, adds hidden state and cannot guarantee one window | Medium | Rejected |
| Merge Panel navigation into `PopupControl` | One class appears to control visibility | Duplicates/contaminates Workflow actuation ownership with entry IA, input and external-target rules | Low | Rejected |
| Capture only text at Panel open and defer OCR input | Smaller prepared model | OCR still suffers action-time focus drift and input no longer has one clear freeze point | Medium | Rejected |
| Single `PrimarySurfaceHost` plus typed prepared input | Matches interaction, keeps semantic owners separate and makes shell/input behavior testable through small interfaces | Requires incremental UI extraction and input-contract migration | High behind the existing feature flag | Accepted |
| Core/UI rewrite | Could normalize every legacy Popup class at once | Broad unrelated risk with no evidence that Workflow or provider cores need rebuilding | Low | Rejected |

## Reversible migration sequence

Each step is cohesive and must keep direct shortcuts working.

1. **Characterize and extend Hotkey tests first.** Add the complete exact-Alt
   conflict matrix and direct-shortcut regression tests without changing
   runtime behavior.
2. **Specify prepared-input contracts.** Add immutable preparation identity,
   `PreparedEntryInput`, source-preview projection and typed completion/retry
   commands. Test selection, clipboard text/image, Workflow lineage, failure,
   cancellation and stale completion through public interfaces.
3. **Move preparation to open.** Preserve the existing external-source capture
   and confirmation rules, but start one identity-scoped preparation after the
   Panel is mounted. Remove action-time capture from the Panel path in the same
   change; do not retain dual input ownership.
4. **Extract the primary host behind a flag.** First make the existing result
   view use `PrimarySurfaceHost` without changing Workflow semantics. Verify
   Popup behavior and `PopupControl` tests remain unchanged.
5. **Mount the Entry view in the same host.** Replace the two-window handoff with
   identity-matched view replacement and rollback. Preserve prior result view
   state when the Panel is opened from an existing Popup.
6. **Unify DPI and bounds.** Move per-window DPI resample, layout, drag and
   current-bounds ownership into the host. Delete duplicated Panel geometry
   lifecycle.
7. **Run Windows release gates.** Validate native Alt behavior, focus, IME,
   numpad, multi-monitor DPI and compositor-visible continuity.
8. **Remove the migration path.** Delete `EntryPanelPopupHandoff` and the old
   independent Panel `CTkToplevel` after the new host is the default. Remove the
   feature flag or leave only a full Panel enable/disable flag; do not leave two
   surface implementations active indefinitely.

Rollback before step 8 selects the old host implementation behind the bounded
feature flag. No rollback changes Action configuration, Workflow history,
provider state or direct shortcuts.

## Required verification

### Fast unit and simulation gates

Hotkey tests must cover:

- 499 ms versus 500 ms and release-before-deadline;
- left/right Alt normalization and Alt auto-repeat;
- Alt then another modifier/key and modifier/key then Alt;
- Alt+Tab, Alt+F4, Alt+Space, Alt+Esc, AltGr, Shift+Alt and Win+Alt producing no
  Panel intent;
- every configured Ctrl+Alt binding, including digits and letters, producing
  exactly one existing Shortcut lifecycle and no Panel intent;
- top-row and numpad selection while Alt remains held;
- local top-row and numpad selection after Alt release;
- repeated holds, missed release settlement, stale timer, injected input,
  shutdown and no double invocation.

Prepared-input and runtime tests must cover:

- Panel appears before blocking preparation begins;
- the original external target is captured before Panel focus;
- selection, clipboard text and clipboard image compatibility;
- Chain selection/full-content priority and exact Workflow/step lineage;
- frozen input does not change after clipboard, focus, navigation, provider or
  Popup changes;
- explicit retry gets a new preparation identity and retains the original
  source identity;
- close/reopen/replace/cancel rejects late completion;
- preview truncation, privacy shape and precise disabled reasons;
- provider busy opens but does not queue; Voice capture rejects opening.

Primary-host tests must cover:

- one top-level shell per visible lifecycle;
- Panel open over an existing result, Esc restore and accepted replacement;
- external Panel to new result replacement;
- off-slot build before atomic mount;
- rollback after build/mount failure;
- exact logical size and physical position before and after replacement;
- user drag persistence, internal overflow and DPI resample ownership;
- no duplicate `PopupControl`, focus owner or toolkit mainloop.

Architecture tests must reject:

- `CTkToplevel` creation by the migrated Entry view or result view outside the
  primary host;
- Panel/runtime access to `PopupControl` internals;
- UI access to clipboard, selection, provider or native Windows details;
- a second clipboard transaction coordinator or raw prepared-input dictionary;
- a second Action admission path or untyped global event mechanism.

### Windows integration and release gates

On a real interactive Windows desktop, verify:

- Alt+Tab, Alt+F4, Alt+Space, Alt+Esc, AltGr and IME retain native behavior;
- left/right Alt, top-row digits and numpad digits behave as specified;
- exact selection is frozen after Alt release without permanently changing the
  clipboard or cursor;
- 100%, 125%, 150% and 200% scaling where hardware is available;
- same-DPI and mixed-DPI multi-monitor placement, drag and Panel/result swap;
- the same top-level window remains visible across one Panel-to-result
  transition;
- 20 ms visible-window sampling reports no desktop gap, blank frame, second
  visible ClipAI primary surface or misplaced opaque frame;
- provider-busy and Voice-active behavior remains truthful.

## Observable completion criteria

The migration is complete only when all of these are true:

1. One visible primary surface hosts Entry and result views for a complete
   Panel-to-Popup lifecycle.
2. Selecting an Action performs no new selection, clipboard or foreground read.
3. The preview and Action execution use the same frozen input identity.
4. Chain admission preserves Workflow and parent-step lineage.
5. Panel and result outer bounds and DPI lifecycle are identical by
   construction, not copied between windows.
6. Native Alt combinations and all direct shortcuts pass the required matrix.
7. The old two-window handoff and action-time Panel capture paths are removed.
8. Targeted unit, architecture, integration and Windows smoke gates pass.

## Consequences

### Positive

- Visual continuity becomes a structural property of one host instead of a
  best-effort timing sequence between two windows.
- Input preview and Action execution share one immutable truth, reducing focus
  drift and making errors visible before admission.
- DPI, bounds, focus and native shell knowledge gain locality in one deep
  module with a small interface.
- Existing Workflow, Popup, provider, recent-action and direct-shortcut owners
  remain intact.

### Negative

- Result and Entry view construction must be separated from top-level window
  construction, which is a non-trivial UI migration.
- A short preparation state appears on every external Panel open.
- Frozen images may temporarily increase memory use; their lifetime must be
  strictly scoped and released.
- Real Windows verification is mandatory because toolkit-only tests cannot
  prove compositor, Alt or mixed-DPI behavior.

## Uncertainty and review triggers

The highest-value remaining evidence is a real Windows trace of selection
capture immediately after a 500 ms Alt hold across common applications and
mixed-DPI monitors. Toolkit simulations cannot establish whether every host
application leaves harmless menu focus after passive Alt observation.

Review this ADR if:

- passive Alt produces unacceptable host-application behavior in measured use;
- a second simultaneous visible primary surface becomes a product requirement;
- a future Action needs an input mode that cannot be safely frozen at Panel
  open;
- prepared images create unacceptable memory pressure;
- Windows measurements show that CustomTkinter cannot safely remount Entry and
  result views in one top-level host.

Any review must preserve the ownership table or explicitly replace it with a
new ADR. It must not reintroduce a second clipboard owner, Action executor,
Workflow state owner, Popup control or unbounded two-window timing workaround.
