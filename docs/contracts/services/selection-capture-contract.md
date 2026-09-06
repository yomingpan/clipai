# Selection capture contract

`SelectionCaptureCoordinator` owns each capture identity, source binding, strategy, and result. `InputResolver` owns input priority. `ClipboardTransactionCoordinator` remains the sole owner of temporary clipboard mutations for both copy and paste.

## Request and evidence

- `begin_capture` performs only cheap native identity reads; it does not call UIA, mutate the clipboard, or move focus. `SelectionCaptureRequest` binds HWND, PID, and native focus. A failed binding remains unavailable; capture must not silently bind a new source.
- Entry Panel binds before presenting its preparing view. Action and contextual-question runtime bind before creating their first Workflow projection. Retries retain the original source and get a fresh preparation-scoped capture identity.
- UIA lives in a hidden child process, receives only source identity via stdin, and returns a typed result via stdout. The parent polls cancellation and enforces a two-second deadline, then terminates/reaps the actual worker process and closes redirected handles.
- UIA focus must belong to the original top-level window. Search only its focused element's ancestry, not arbitrary desktop elements. Password controls are unavailable. Full document text, Name, and Value cannot substitute for selection.
- UIA focus and selection ranges are checked again after reading. Original logical lines, indentation, and trailing whitespace survive; CR/CRLF are represented as LF. Disjoint ranges are joined with LF in provider order.

## Results

| Status | Meaning | Automatic clipboard fallback |
|---|---|---|
| selected | Nonempty text from the validated selection | No |
| none | Supported source explicitly reports only caret ranges | Yes |
| unknown | Unsupported, absent ranges, timeout, source change, or read failure | No |
| cancelled | Operation no longer wanted | No |

Positive selection evidence with failed text retrieval may use the existing controlled Ctrl+C transaction. A source-bound `copy_selection_only` capability may also permit that transaction: it means a verified adapter recognizes a source whose Copy command only copies selected content, not that a selection exists. Unsupported editors without this capability must not receive blind Ctrl+C: some copy the whole current line without a selection. Source checks precede clipboard mutation and copy and continue during polling. Copy timeout and empty copy never establish `none`, even for a verified source, and never permit automatic old-clipboard fallback.

The first verified profile is Anki's main card WebView: process `anki`, Qt focused
ancestry containing `MainWebView`, and exact top-level `AnkiQt` HWND/PID. Native
and virtual focus, source ancestry and password checks still apply. Toolbars,
editors, unrelated Qt apps, siblings and arbitrary unsupported controls are not
covered. `platform/selection_copy_profiles.py` owns this recognition; services
consume only the typed capability and reuse the single clipboard transaction
owner. See ADR-0015 for evidence, limitations and the review trigger.

## Entry Panel and consumer policy

`PreparedInput` retains the selection outcome and a frozen clipboard fallback. Unknown selection disables selection-dependent Actions without erasing explicitly clipboard-only capabilities. `UseEntryPanelClipboard(panel_id)` applies only to the current Panel with prepared clipboard content, changes the source preview to clipboard, and never rereads live clipboard state. A stale panel intent has no effect. Cancellation never creates prepared input.

Direct visible Actions and Entry Panel both call `InputResolver.prepare_input` and
consume immutable `PreparedInput.resolve(mode)`. Clipboard-only Actions skip the
selection probe. `PreparedInput.use_clipboard()` is the shared explicit source
choice and never rereads external state. Unsupported selection is never converted
to confirmed-none. Speech retains typed `SelectionUnavailableError` behavior.
Global speech binds its capture request at intent admission, then resolves text
in the supervised media worker with the speech operation's cancellation token.
Job creation must not run UIA or compatibility copy on the Tk command pump.
Input failure settles the existing output operation as failed and notifies the
user without creating a Popup or invoking TTS. Capture cancellation settles as
cancelled without an error notification. Superseded jobs cannot notify or settle
the replacement operation; a rejected worker submission releases its speech job.

`WorkflowController` owns direct Action input recovery in `AWAITING_INPUT_CHOICE`,
including one recovery identity, the original resolved Action/press variant,
invocation lineage, and frozen input. There is no active provider request while
waiting for the choice. `UseWorkflowClipboard(workflow_id, recovery_id)` consumes
the matching choice once; runtime resumes the same Workflow with a fresh invocation
and its existing provider binding. Cancel, stop, replacement and close invalidate
the choice. Failed capture leaves successful-step history intact but exposes no
output actions or editable input form.

Popup presentation projects the frozen clipboard preview and one recovery button.
Initial input-reading views show without requesting focus. A 15-second UI lifecycle
timer emits `ExpireInputRecovery`; runtime closes only a matching, still-waiting,
unfocused and unpinned Workflow. Expiry never closes a resumed/newer task. Focused
or pinned recovery stays available for reading and keyboard interaction. Entry
Panel retains its navigation and does not expire; both surfaces use the same
frozen source decision. A missing compatible clipboard yields guidance without
an enabled recovery button.

Diagnostics include operation identity, source token, status, reason, strategy,
elapsed time, and restoration outcome, never selected text or clipboard content.

## Validation

Simulated tests cover unknown versus none, stale source and late cancellation, timeout cleanup, provider ancestry/focus/range changes, exact whitespace preservation, unavailable clipboard, and explicit frozen clipboard choice. Architecture tests forbid the old string-only selection port and require native probe wiring with one clipboard transaction owner.

Opt-in Windows test: `python -m pytest tests/platform/test_selection_uia_integration.py -m integration`. It opens an owned temporary RichTextBox and checks selected text, repeated identical selection, and caret-only state, then cleans up its host. Run on an interactive desktop. This is not a substitute for testing the user's specific apps, web pages, PDFs, and permission levels.

Limitations: UIA is not an atomic snapshot at physical key-down; sources are bound at intent admission and verified around the subsequent read. Clipboard sequence changes do not provide cryptographic proof of the copy producer. Unsupported or incomplete providers require a separate verified adapter; screenshots are not silently substituted.
