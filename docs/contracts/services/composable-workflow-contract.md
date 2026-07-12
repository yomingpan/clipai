# Composable Workflow Contract

## Intent

Popup 是可連續處理的 workflow surface，不只是單次 action 的輸出。每次 action execution 是 immutable invocation；一個 workflow 保存成功 step history，並由單一 `WorkflowController` 擁有狀態。

## Invocation

`ActionInvocation` 必須明確包含 invocation ID、action/press type、input target、result route、workflow ID 與 parent step ID。Runtime 不得依 action ID 決定 input 或 output policy。

每個 invocation 擁有獨立 cancellation token。Workflow 只接受目前 active invocation ID 的 progress、success 或 failure；被取代的 worker 晚到時不得更新 popup或回報成功。

## Input Policy

- `external_text`：selection-first、clipboard fallback，不使用 popup result。
- `contextual_text`：最後互動 popup 的非空 selection 優先，否則使用 displayed successful step；沒有有效 popup context 時 fallback 至 external text。

UI 透過 read-only `ActiveWorkflowContext` port 提供 workflow、step、content 與 selection。Services 不讀 Tk widget，platform hotkey listener 不理解 popup context。

## History

- 只有 successful result 成為 workflow step。
- 新 invocation processing 時保留上一個成功內容並顯示真實 status。
- Failure 保留既有 content/history。
- Back 只切換已完成 step，不呼叫 provider。
- 從歷史 step 成功產生新結果時，捨棄該 step 之後的 forward history；失敗不得修改 history。
- History 僅存在於 popup workflow lifetime，關閉後不持久化。

## Routing

Action execution 產生 `ProcessedResult`，再由 typed `ResultRoute` 決定 popup 或 speech destination。Provider 不呼叫 UI/TTS；UI 不呼叫 provider。第一階段產品功能只配置 popup route，speech route 保留可測 contract。

## Shortcut Sequence Seam

Platform 只輸出 atomic `shortcut_id + press_type`。Runtime enqueue `ShortcutTriggered`，再由 `ShortcutIntentCoordinator` 解析。未來 sequence coordinator 必須替換此 policy seam，不得把 timeout/sequence state 放進 platform listener。
