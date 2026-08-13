# Popup Output Actions Contract

Speaker、copy、paste、archive 使用 selection-first：有非空 selection 時使用 selection，否則使用目前 displayed step 的 canonical content。UI 將 semantic text 與 operation ID 放進 typed command，runtime 不讀 Tk widget。

所有 output action 先投影 `pending`，並以 operation ID 拒絕 stale completion。Copy、archive 與 speech 可進入 `succeeded / failed / cancelled`；Paste 不可宣稱已被目標程式消費，因此只有 `failed / cancelled / dispatched_unconfirmed / cleanup_failed` 四種 terminal acknowledgement。

`OutputOperationCoordinator.settle(OutputOperationResult)` 是唯一 terminal
入口，並同時結束 tracker handle 與 interruption lease。`begin()` 只投影
pending；submit failure 必須轉為 terminal failure。Stale result 比對
operation id、Workflow id 與 kind 失敗時，不得碰目前 handle 或 lease。

`PasteOperationCoordinator` 是 Paste active membership、取消、dispatch truth 與 terminal outcome 的單一 owner。整個 container 同時只允許一個 Paste Operation；重疊請求立即以原 operation ID 回報失敗，不排隊，也不取代進行中的操作。Runtime 只排程 operation identity，不持有 concrete Paste handle 或 Paste registry。

Paste 使用共用 `ClipboardTransactionCoordinator`：保存完整文字／圖片 snapshot、寫入文字、記錄 owned sequence、送出 paste，並只在 sequence 未被使用者或其他程式更新時還原。它不得建立第二套 clipboard lock、snapshot 或 restoration owner。

Clipboard Preservation 採 fail-closed。只要 adapter 無法安全保存任一非冗餘原生格式，就必須在 clipboard mutation 與 Paste Dispatch 前以 `failed / not_dispatched` 結束。若 dispatch 已發生，cleanup failure 不得把 delivery truth 改寫成一般失敗；必須回報 `cleanup_failed` 並警告使用者先確認目標，避免盲目重試造成重複內容。

取消只表示 intent。Worker 尚未開始時可在 cleanup 後立即回報 `cancelled / not_dispatched`；worker 已開始後必須等待 coordinator 確認 dispatch 與 cleanup truth。Coordinator 恰好一次以 `PasteOperationCompleted` 經 application command queue 回報；TaskSupervisor task completion 不代表 Paste completion。

Popup visibility 與 Workflow lifetime 分離。未 pinned Popup 收到 `dispatched_unconfirmed` 後保持隱藏並釋放 semantic Foreground Workflow，但 Workflow membership 與結果仍保留，不能把 view 隱藏誤解為 operation success 或 Workflow deletion。Pinned Popup 可恢復顯示警告；`failed`、`cancelled` 與 `cleanup_failed` 依 UI contract 恢復 surface，但只有 dispatch 前 `failed` 可以主動取回 focus。

Popup focus 必須同時有 native foreground 與 toolkit focus 證據；單獨的
`<FocusIn>` 不是 confirmed focus。Alt+Tab、taskbar switch 或外部程式搶走
foreground 以 `ForegroundLeftApplication` 進入同一 transition owner。Paste 與
owned dialog 是刻意讓出 foreground 的 guard，不得被解讀為 outside close。

Speech preprocessing 屬於 service，移除 Markdown heading、emphasis、list marker、code fence 與 URL 噪音，但不得修改 popup、copy 或 paste 的原文。

Popup、global hotkey 與 shortcut-sequence speech 共用一個 `SpeechCoordinator`。TTS 是單一資源，但取消必須比對 operation ID；舊 popup 關閉、舊 worker 完成或舊 handle 取消，都不得停止或清除新 operation 的 speaking state。

Composable workflow 中，copy/paste/speak 的 fallback text 是目前 displayed step，而非永遠使用最新 step。Back navigation 不呼叫 provider，且 popup selection 仍優先於 displayed step content。
