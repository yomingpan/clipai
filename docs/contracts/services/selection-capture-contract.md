# Selection capture contract

`SelectionCaptureCoordinator` owns each capture identity, source binding, strategy, and result. `InputResolver` owns input priority. `ClipboardTransactionCoordinator` remains the sole owner of temporary clipboard mutations for both copy and paste.

## Request and evidence

- `begin_capture` performs only cheap native identity reads; it does not call UIA, mutate the clipboard, or move focus. `SelectionCaptureRequest` binds HWND, PID, and native focus. A failed binding remains unavailable; capture must not silently bind a new source.
- Entry Panel binds before presenting its preparing view. Action and contextual-question runtime bind before creating their first Workflow projection. Retries retain the original source and get a fresh preparation-scoped capture identity.
- UIA lives in a hidden child process and exchanges newline-delimited, identity-only requests and typed results. One probe owns one healthy worker for a single top-level HWND/PID, serves requests sequentially, and retires it after 64 requests. Switching top-level source retires the old worker before reuse. Timeout, cancellation, malformed results and provider/restore failure retire and reap the worker immediately. An overlapping request uses an isolated one-request overflow process; there is no disposable worker pool.
- `SelectionCaptureCoordinator` alone gates compatibility Copy on physical `ctrl`, `alt`, and `shift` release. Source validation and read-only UIA run immediately, including while modifiers remain held. The release gate runs only for an `unknown` outcome with positive `selection_detected` or verified `copy_selection_only` evidence; it retains the existing one-second deadline. Timeout returns `modifier_timeout`; cancellation returns `cancelled`; neither copies nor mutates the clipboard. See [ADR-0021](../../adr/0021-selection-modifier-release-scoped-to-copy-fallback.md).
- UIA focus must belong to the original top-level window. Search only its focused element's ancestry, not arbitrary desktop elements. Password controls are unavailable. Full document text, Name, and Value cannot substitute for selection.
- UIA focus and selection ranges are checked again after reading. Original logical lines, indentation, and trailing whitespace survive; CR/CRLF are represented as LF. Disjoint ranges are joined with LF in provider order.

The capture order is fixed:

0. Already cancelled: return `cancelled`.
1. Missing bound source: return `source_unavailable`.
2. Validate source-current #1; failure returns `source_changed` without probing.
3. Probe the bound source without polling modifiers.
4. Check cancellation after probing; a cancelled probe also terminates capture.
5. If `focus_restored`, recapture against the original window. A missing or different HWND/PID returns `source_changed` with strategy `uia`; otherwise use the rebased source.
6. Validate source-current #2; failure returns `source_changed` with strategy `uia`.
7. Only an unknown outcome with positive selection evidence or verified selection-only Copy waits for modifiers. Timeout/cancellation terminates without Copy or clipboard writes.
8. Validate source-current #3; failure returns `source_changed` with strategy `uia`, without Copy.
9. Only the authorized Copy path calls `ClipboardTransactionCoordinator.capture_selection`, with the source-current callback retained throughout the transaction. Other paths return the UIA outcome.
10. Exceptions return `capture_failed`. Finally emit the existing content-free log format unchanged:

```text
Selection capture operation_id=%s target=%s status=%s reason=%s strategy=%s focus_restored=%s elapsed_ms=%d
```

## Results

### Worker lifecycle

`WindowsSelectionProbe` owns all launched and launching processes, including
overflow. `stop()` permanently closes admission, initiates cleanup concurrently,
and waits at most two seconds total, including graceful exit, forced termination
and exit confirmation. A subsequent `start()` does not reopen this owner.
Unconfirmed cleanup raises `RuntimeError`; runtime teardown logs it and continues
other cleanup. Failed or late-launch workers remain owned, and a late process
still receives cleanup. Repeating `stop()` can confirm a completed late cleanup.
No timeout is represented as confirmed process exit.

Retiring an unhealthy owned worker clears its reusable pointer, source and request
count before cleanup. Unconfirmed retirement warns and retains that worker in the
single registry, while the next capture may create a new owned worker. Cleanup
failure still raises after stop closes admission. An empty/error response, or
invalid response interrupted during retirement or cancellation, is `cancelled`
rather than a worker fault.

The private native result carries explicit `worker_reusable` truth separately
from the semantic selection outcome. Transport requires a boolean field and
validates the response; diagnostic reason spelling never determines reuse.
Provider, text retrieval and focus restoration failures explicitly reject reuse
at their detection sites. Missing or malformed lifecycle evidence retires the
worker. Lifecycle metadata stays in platform and does not enter core outcomes.

Process launch and pipe I/O never hold the lifecycle admission lock. Retirement
can interrupt an outstanding exchange; pipe cleanup is only confirmed after the
process exits and exchange/close threads finish. OS launch/cleanup that cannot
settle within the bound is reported rather than blocking shutdown indefinitely.

### Semantic outcomes

Core owns the closed `SelectionReason` wire vocabulary and its complete
`SelectionGuidanceCategory` mapping. `selection_guidance_category` treats empty
or unknown reasons as `NO_SELECTION`. `SelectionCaptureOutcome.classification`
prioritizes selected/cancelled status, then classifies the modifier category as
`NEEDS_MODIFIER_RELEASE`; other unresolved outcomes are `UNRESOLVED`. Consumers
use typed classification/category, never reason-string comparisons or a second
reason collection. Reason spellings and the capture log remain compatible.

| Status | Meaning | Automatic clipboard fallback |
|---|---|---|
| selected | Nonempty text from the validated selection | No |
| none | Supported source explicitly reports only caret ranges | Yes |
| unavailable | No selection adapter is configured for this runtime | Yes |
| unknown | Unsupported, absent ranges, timeout, source change, or read failure | No |
| cancelled | Operation no longer wanted | No |

Positive selection evidence with failed text retrieval may use the existing controlled Ctrl+C transaction. A source-bound `copy_selection_only` capability may also permit that transaction: it means a verified adapter recognizes a source whose Copy command only copies selected content, not that a selection exists. Unsupported editors without this capability must not receive blind Ctrl+C: some copy the whole current line without a selection. Source checks precede clipboard mutation and copy and continue during polling. Copy timeout and empty copy never establish `none`, even for a verified source, and do not permit shared-resolver or direct-consumer automatic old-clipboard fallback. The Entry-specific frozen-input exception is evaluated separately below.

The first verified profile is Anki's main card WebView: verified `anki.exe`, or
the launcher layout `AnkiProgramFiles/python/cpython-<version>-windows-x86_64-none/pythonw.exe`,
Qt focused ancestry containing `MainWebView`, and exact top-level `AnkiQt` HWND/PID. Native
and virtual focus, source ancestry and password checks still apply. Toolbars,
editors, unrelated Qt apps, siblings and arbitrary unsupported controls are not
covered. `platform/selection_copy_profiles.py` owns this recognition; services
consume only the typed capability and reuse the single clipboard transaction
owner. See ADR-0015 for evidence, limitations and the review trigger.

A verified Anki shell may authorize one narrower side effect when its card is
gray/unfocused and focus remains on inert `QWidget`/`QObject` shell ancestry: the
profile returns an immutable focus-repair plan, and the generic worker finds its
target, calls `SetFocus` only on the inner card element, polls for bounded
settlement, and rereads focused ancestry. Menu, editor, toolbar, sibling WebView,
and arbitrary Qt ancestry are rejected before repair. It does
not activate a top-level window, synthesize input, or touch the clipboard. The
typed `focus_restored` flag requires the coordinator to recapture the same
top-level HWND/PID before staleness validation. A missing/different source is
`source_changed`. Copy trust is still granted only by the restored focused
`MainWebView` ancestry; application identity alone never grants Copy.

## Entry Panel and consumer policy

### Bounded external-window readiness

Bare Alt Entry Panel gestures also require native menu masking. The platform
hotkey dispatcher owns the consumed hold and whether its native release was seen;
the Windows hook inserts a balanced unassigned `VK_E8` pair before forwarding that
hold's physical Alt-up. This prevents Qt/Windows menu navigation from moving
virtual focus off the selected control while the same HWND remains foreground.
Short Alt, unclaimed chords and injected input are not masked. A native release
seen before the hold deadline rejects the late timer even when pynput's semantic
release is still queued. No new focus restoration or capture owner is introduced.
The Anki copy profile and focus-repair plan reject menu-bar ancestry.

Entry Panel input preparation passes an immutable `ExternalWindowWaitPolicy`
through `ExternalWindowActivator`: 3 seconds of combined activation and
post-capture confirmation time, with a waiting notice after 500 ms. Selection
reading has its own cancellation/timeout and does not consume this focus budget.
Runtime passes only the remaining budget to post-capture confirmation; retries
explicitly requested by the user create a new preparation identity and budget.
The native adapter returns immediately when the exact original target is ready,
validates the original HWND/PID throughout waiting, and stops on cancellation or
invalid source. It never substitutes the current foreground window. Native API
calls and OS scheduling can delay observation beyond the deadline; the bound
limits polling/retries, not the duration of a blocked OS call.

Only actual native waiting emits `on_waiting`. The worker enqueues
`EntryPanelInputPreparationProgress(panel_id, preparation_id, phase)` once per
waiting episode; runtime accepts
it only for the matching, still-preparing operation. The coordinator projects
“正在等待原視窗就緒…（Esc 可取消）” in the existing neutral message area. No timer,
extra capture, UI-thread native work, or focus request is introduced by the
notice. Activation success returns the message to reading while selection is
captured; a subsequent confirmation wait can report waiting again using the
remaining notice threshold/budget. Completion clears it; timeout projects “等待原視窗就緒逾時，請重試。”;
invalid-source guidance remains distinct. Esc closes/cancels preparation, and
late notices cannot resurrect a closed, retried, failed, or completed operation.

`target_focus_timeout` means foreground did not return within the bound;
`target_changed` means source validation failed. Neither permits implicit
clipboard fallback. Paste retains its existing default activation timing;
the longer readiness policy is explicitly supplied by Entry Panel only.
Activation, selection capture, and confirmation log separate elapsed times and
operation identities without source/clipboard content.

`PreparedInput` retains the selection outcome and a frozen clipboard fallback. A missing selection adapter uses that fallback automatically and the resolved document identifies `clipboard` as its source. For the Entry Panel only, `allows_entry_panel_clipboard_fallback` is the sole automatic decision: unknown, not requiring modifier release, and frozen clipboard text/image available. Such outcomes apply `PreparedInput.use_clipboard()`; unknown with no clipboard remains retryable. `modifier_timeout` keeps a failed preview reading “請先放開按鍵，再按重試。” and exposes the explicit clipboard choice when frozen input is available. That branch precedes general unknown/cancelled guidance. Direct Actions, contextual questions and global speech retain correctness-first `selection_unknown` behavior. `UseEntryPanelClipboard(panel_id)` remains an idempotent typed intent against current frozen input and never rereads live clipboard state. A stale panel intent has no effect. Cancellation never creates prepared input.

Direct visible Actions and Entry Panel both call `InputResolver.prepare_input` and
consume immutable `PreparedInput.resolve(mode)`. Clipboard-only Actions skip the
selection probe. `PreparedInput.use_clipboard()` is the shared explicit source
choice and never rereads external state. Unsupported source evidence is never converted
to confirmed-none; only an unconfigured selection adapter and confirmed `none` permit
automatic clipboard fallback. Speech retains typed `SelectionUnavailableError` behavior
for unknown source evidence and uses clipboard text when no selection adapter is configured.
Global speech binds its capture request at intent admission, then resolves text
in the supervised media worker with the speech operation's cancellation token.
Job creation must not run UIA or compatibility copy on the Tk command pump.
Input failure settles the existing output operation as failed and notifies the
user without creating a Popup or invoking TTS. Capture cancellation settles as
cancelled without an error notification. Superseded jobs cannot notify or settle
the replacement operation; a rejected worker submission releases its speech job.
Global speech input errors with a reason use `selection_failure_guidance`, which
maps core's engine/focus/modifier/no-selection category to problem-and-advice
copy beginning “讀不到反白的文字：”. Engine failures suggest retry and restarting
ClipAI if persistent. Errors without a reason retain their original message.

`WorkflowController` owns direct Action input recovery in `AWAITING_INPUT_CHOICE`,
including one recovery identity, the original resolved Action/press variant,
invocation lineage, and frozen input. There is no active provider request while
waiting for the choice. `UseWorkflowClipboard(workflow_id, recovery_id)` consumes
the matching choice once; runtime resumes the same Workflow with a fresh invocation
and its existing provider binding. Cancel, stop, replacement and close invalidate
the choice. Failed capture leaves successful-step history intact but exposes no
output actions or editable input form.

Popup presentation projects the frozen clipboard preview and one recovery button.
Initial input-reading views show without requesting focus. Only a transition
from CREATED/READING_INPUT into AWAITING_INPUT_CHOICE with an available clipboard
choice requests Popup focus. The button reads 使用剪貼簿執行（Enter）.
`KeyboardConfirmGate` requires focus inside the current mounted view, 300 ms
settlement, a fresh press followed by release, and no modifiers except lock
bits 0x0002/0x0008/0x0010. Early presses, held-elsewhere keys, auto-repeat,
focus loss and hidden/replaced options cannot confirm. Option changes restart
the gate; each recovery ID emits at most one confirmation, then shows disabled
正在接續…. See `tests/ui/test_keyboard_confirm_gate.py`,
`tests/ui/test_input_recovery.py` and `tests/ui/test_result_dialog.py`.
At focus entry, injected `KeyboardStateReader` samples the physical Return
state through the existing platform key-state adapter. Held or unavailable
state blocks a first delayed repeat/release even when this Popup never received
the external key-down; after release, a new press can qualify. UI does not call
Win32 or introduce a keyboard-activity monitor. The platform VK_RETURN mapping
also covers keypad Enter (`tests/platform/test_keyboard_state.py`).

A 15-second UI lifecycle
timer emits `ExpireInputRecovery`; runtime closes only a matching, still-waiting,
unfocused and unpinned Workflow. Expiry never closes a resumed/newer task. Focused
or pinned recovery stays available for reading and keyboard interaction. Entry
Panel retains its navigation and does not expire; both surfaces use the same
frozen source decision. A missing compatible clipboard yields guidance without
an enabled recovery button.

## Read-only UIA standby

Typed `selection_uia_standby` defaults to true. `WindowsSelectionProbe` owns at
most one unbound standby worker; its readiness handshake follows CLR preload
and never samples a focused element. A new source consumes a healthy standby
or retires it and cold-starts, then binds the exact source and queries. Requests
replenish standby without creating a second worker registry. With the setting
false, start creates no worker and capture remains lazy. See
`tests/platform/test_selection_uia.py`, `test_selection_standby_integration.py`
and `tests/app/test_config.py`.

Retirement kills/reaps the owned read-only worker rather than spending a CLR
graceful-exit delay on interactive capture. stop retains the shared two-second
cleanup budget. The worker lifecycle integration suite and
[S8 evidence](../../adr/0022-right-alt-inline-pill-and-input-recovery.md)
cover source replacement, private memory and zero residual processes; timeout
or source_changed is still unknown, never confirmed-none.

Diagnostics include operation identity, source token, status, reason, strategy,
elapsed time, and restoration outcome, never selected text or clipboard content.
The content-free probe hashes HWND/PID identity and never emits executable paths.

## Validation

Simulated tests cover unknown versus none, stale source and late cancellation, timeout cleanup, provider ancestry/focus/range changes, exact whitespace preservation, unavailable clipboard, and explicit frozen clipboard choice. Architecture tests forbid the old string-only selection port and require native probe wiring with one clipboard transaction owner.

`selection_reliability_gate.py --iterations 3` covers 27 scenarios with virtual
monotonic/wait clocks, compares outcome fingerprints across iterations, and
reports six invariants: policy, clipboard_dirty, unknown_as_none, blind_copy,
copy_while_held and text_mismatch. An all-none mutation must fail. Simulation
latency is not device evidence. Architecture tests enforce the core reason set,
consumer classification and Tk-free canonical content ownership.

`selection_desktop_loop.py` has separate auto and attended modes. Auto uses an
owned WinForms RichTextBox, one unrecorded clipboard-verified warmup, and adapter
modifier state; it never injects keys. Attended requires physical keys, matches
fresh application log bytes to the owned window token, and waits for the human's
“下一案” acknowledgement after releasing keys and closing the Panel. Capture-log
waiting is bounded to 15 seconds per case. The host receives foreground focus
before test selection is set. Use `--log logs/clipai.log` for this source checkout;
the default is `%LOCALAPPDATA%/ClipAI/logs/clipai.log`.

Exit codes are 0 pass, 1 failed, 2 invalid arguments and 3 environment blocked.
Missing main application, elevated harness or noninteractive desktop blocks
attended. For clipboard calls, only exact `OSError("Clipboard is busy")` is retried, at most 20 attempts
with 0.25-second intervals; exhaustion blocks, other OSErrors propagate. Partial
case counts and warmup failures remain explicit, and a blocked result cannot
count as acceptance. Cleanup is probe stop, host shutdown/kill after two seconds,
then conditional clipboard restoration. JSONL contains metadata/hashes only.

Opt-in Windows test: `python -m pytest tests/platform/test_selection_uia_integration.py -m integration`. It opens an owned temporary RichTextBox and checks selected text, repeated identical selection, and caret-only state through one probe, then cleans up both probe and host in nested finally blocks. Run on an interactive desktop. This is not a substitute for testing the user's specific apps, web pages, PDFs, and permission levels.

`tests/platform/test_selection_worker_lifecycle.py -m integration` uses controlled
real subprocesses without UIA, clipboard or external source access. It verifies
reuse, retirement, malformed replies, EOF, cancellation, concurrent overflow stop,
terminal admission and late-launch cleanup against the public probe interface.

Limitations: UIA is not an atomic snapshot at physical key-down; sources are bound at intent admission and verified around the subsequent read. Clipboard sequence changes do not provide cryptographic proof of the copy producer. Unsupported or incomplete providers require a separate verified adapter; screenshots are not silently substituted.
