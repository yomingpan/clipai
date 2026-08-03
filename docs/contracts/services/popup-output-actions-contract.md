# Popup Output Actions Contract

Speaker、copy、paste、archive 使用 selection-first：有非空 selection 時使用 selection，否則使用目前 displayed step 的 canonical content。UI 將 semantic text 與 operation ID 放進 typed command，runtime 不讀 Tk widget。

所有 output action 先投影 `pending`，並以 operation ID 拒絕 stale completion。Copy、archive 與 speech 可進入 `succeeded / failed / cancelled`；Paste 不可宣稱已被目標程式消費，因此只有 `failed / cancelled / dispatched_unconfirmed / cleanup_failed` 四種 terminal acknowledgement。

`PasteOperationCoordinator` 是 Paste active membership、取消、dispatch truth 與 terminal outcome 的單一 owner。整個 container 同時只允許一個 Paste Operation；重疊請求立即以原 operation ID 回報失敗，不排隊，也不取代進行中的操作。Runtime 只排程 operation identity，不持有 concrete Paste handle 或 Paste registry。

Paste 使用共用 `ClipboardTransactionCoordinator`：保存完整文字／圖片 snapshot、寫入文字、記錄 owned sequence、送出 paste，並只在 sequence 未被使用者或其他程式更新時還原。它不得建立第二套 clipboard lock、snapshot 或 restoration owner。

取消只表示 intent。Worker 尚未開始時可在 cleanup 後立即回報 `cancelled / not_dispatched`；worker 已開始後必須等待 coordinator 確認 dispatch 與 cleanup truth。Coordinator 恰好一次以 `PasteOperationCompleted` 經 application command queue 回報；TaskSupervisor task completion 不代表 Paste completion。

Speech preprocessing 屬於 service，移除 Markdown heading、emphasis、list marker、code fence 與 URL 噪音，但不得修改 popup、copy 或 paste 的原文。

Popup、global hotkey 與 shortcut-sequence speech 共用一個 `SpeechCoordinator`。TTS 是單一資源，但取消必須比對 operation ID；舊 popup 關閉、舊 worker 完成或舊 handle 取消，都不得停止或清除新 operation 的 speaking state。

Composable workflow 中，copy/paste/speak 的 fallback text 是目前 displayed step，而非永遠使用最新 step。Back navigation 不呼叫 provider，且 popup selection 仍優先於 displayed step content。
