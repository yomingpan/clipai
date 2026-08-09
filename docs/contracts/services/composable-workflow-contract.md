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
- Back 不呼叫 provider。一般 Workflow 只切換已完成 step；第一個 Action result 若帶有 Voice Draft origin，Back 會回到該 Draft 的 Review projection。
- 從歷史 step 成功產生新結果時，捨棄該 step 之後的 forward history；失敗不得修改 history。
- History 僅存在於 visible Workflow lifetime，關閉後不持久化。

## Voice Draft Seam

- Voice Draft 是 Workflow lifetime 內的 ephemeral canonical text，不是另一個 Session，也不持久化。
- `WorkflowController` 是 snapshot、history、lock scope 與 UI render 的唯一 owner；`services/voice_draft.py` 只計算 immutable transition，不持有狀態或呼叫外部能力。
- Interim recognition 只供即時預覽，不得成為 canonical Draft。只有 terminal recognition result 可以套用至 Draft。
- Recognition 開始時凍結 insertion target 與 Draft revision；若使用者在完成前編輯 Draft，過時結果不得覆寫較新的內容。
- 由 Voice Draft 執行 Action 時，origin 隨 successful step 保存；從第一個 Action result Back 時，回到同一份 Draft Review，不重新呼叫 provider。

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

Platform 輸出 ordered `ShortcutInputEvent` lifecycle。Runtime 原樣 enqueue，
並把未被 guide quarantine 的 `ShortcutPressInvoked` 交由
`ShortcutSequenceCoordinator` 解析。
Coordinator 是 shortcut sequence policy 與 lifecycle 的單一 owner；
timeout、waiting、cancellation 與 speech routing state 不得放進 platform
listener。
