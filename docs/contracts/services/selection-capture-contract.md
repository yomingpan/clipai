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

Positive selection evidence with failed text retrieval may use the existing controlled Ctrl+C transaction. Unsupported editors must not receive blind Ctrl+C: some copy the whole current line without a selection. Source checks precede clipboard mutation and copy and continue during polling. Copy timeout and empty copy never establish `none`.

## Entry Panel and consumer policy

`PreparedEntryInput` retains the selection outcome and a frozen clipboard fallback. Unknown selection disables selection-dependent Actions without erasing explicitly clipboard-only capabilities. `UseEntryPanelClipboard(panel_id)` applies only to the current Panel with prepared clipboard content, changes the source preview to clipboard, and never rereads live clipboard state. A stale panel intent has no effect. Cancellation never creates prepared input.

Source errors propagate as typed `SelectionUnavailableError` for direct Actions and speech. Diagnostics include operation identity, source token, status, reason, strategy, elapsed time, and restoration outcome, never the selected text or clipboard content.

## Validation

Simulated tests cover unknown versus none, stale source and late cancellation, timeout cleanup, provider ancestry/focus/range changes, exact whitespace preservation, unavailable clipboard, and explicit frozen clipboard choice. Architecture tests forbid the old string-only selection port and require native probe wiring with one clipboard transaction owner.

Opt-in Windows test: `python -m pytest tests/platform/test_selection_uia_integration.py -m integration`. It opens an owned temporary RichTextBox and checks selected text, repeated identical selection, and caret-only state, then cleans up its host. Run on an interactive desktop. This is not a substitute for testing the user's specific apps, web pages, PDFs, and permission levels.

Limitations: UIA is not an atomic snapshot at physical key-down; sources are bound at intent admission and verified around the subsequent read. Clipboard sequence changes do not provide cryptographic proof of the copy producer. Unsupported or incomplete providers require a separate verified adapter; screenshots are not silently substituted.
