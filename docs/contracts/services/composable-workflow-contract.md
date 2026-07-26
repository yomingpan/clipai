# Composable Workflow Contract

## Intent

Visible Workflow 是可連續處理的互動 surface，不只是單次 Action 的輸出。每次 Action execution 是 immutable invocation；一個 Workflow 保存成功 step history，並由單一 `WorkflowController` 擁有內部狀態。

## Invocation

`ActionInvocation` 必須明確包含 invocation ID、action/press type、input target、result route、workflow ID 與 parent step ID。Runtime 不得依 action ID 決定 input 或 output policy。

每個 invocation 擁有獨立 cancellation token。Workflow 只接受目前 active invocation ID 的 progress、success 或 failure；被取代的 worker 晚到時不得更新 visible Workflow surface 或回報成功。

## Input Resolution

Runtime owns the semantic Foreground Workflow identity. UI supplies a read-only
`WorkflowContextReader` that returns content and selection for the workflow ID
chosen by runtime policy; toolkit focus only reports activation candidates.

- 所有 text-capable Action 固定優先使用 Foreground Workflow surface 的非空 selection。
- 沒有 selection 時使用 displayed successful step 的 canonical content。
- 沒有有效 Workflow context 時才套用 Action 的 `external_fallback`：`selection_or_clipboard` 或 `clipboard`。
- 舊 `input_policy` 只保留一個 release 的 config-loader 相容期，不進入 domain model。

## History

- 只有 successful result 成為 workflow step。
- 新 invocation processing 時保留上一個成功內容並顯示真實 status。
- Failure 保留既有 content/history。
- Back 只切換已完成 step，不呼叫 provider。
- 從歷史 step 成功產生新結果時，捨棄該 step 之後的 forward history；失敗不得修改 history。
- History 僅存在於 visible Workflow lifetime，關閉後不持久化。

## Workflow Lifetime

- `WorkflowRuntimeModule` is the single owner of workflow membership, the
  semantic Foreground Workflow identity, and each workflow's captured provider
  binding.
- A workflow keeps the provider and model binding captured when it starts;
  follow-ups do not switch when runtime configuration changes.
- Visible and headless workflows share the same identity rules. Headless
  workflows are never foreground, but the lifetime model does not impose a
  global headless singleton.
- Duplicate workflow registration is rejected. Ending an unknown or
  already-ended workflow is an idempotent no-op.
- Cancellation and close release the workflow record. Visible completion keeps
  the record available for follow-up until close; headless completion releases
  it immediately.
- Worker completion and failure re-enter the runtime through typed commands
  before lifetime state changes.

## Routing

Action execution 產生 `ProcessedResult`，再由 typed `ResultRoute` 決定 visible Workflow 或 speech destination。Visible route 投影到既有 Workflow surface；speech route 使用 headless Workflow 執行，完成後立即釋放 membership。Provider 不呼叫 UI/TTS；UI 不呼叫 provider。

## Shortcut Sequence Seam

Platform 只輸出 atomic `shortcut_id + press_type`。Runtime enqueue `ShortcutTriggered`，再由 `ShortcutIntentCoordinator` 解析。未來 sequence coordinator 必須替換此 policy seam，不得把 timeout/sequence state 放進 platform listener。
