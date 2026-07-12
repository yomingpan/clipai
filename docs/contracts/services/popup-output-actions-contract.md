# Popup Output Actions Contract

Speaker、copy、paste、archive 使用 selection-first：有非空 selection 時使用 selection，否則使用目前 displayed step 的 canonical content。UI 將 semantic text 與 operation ID 放進 typed command，runtime 不讀 Tk widget。

所有 output action 依序投影 `pending -> succeeded/failed/cancelled`，並由 operation ID 防止舊 completion 覆蓋新操作。Copy、archive 與 paste 都由 worker 執行；Paste 只有成功後才關閉 popup，失敗保留 popup 並顯示錯誤。

Paste 使用共用 clipboard transaction：保存完整文字/圖片 snapshot、寫入文字、記錄 owned sequence、送出 paste，並只在 sequence 未被使用者或其他程式更新時還原。Delay 必須可注入。

Speech preprocessing 屬於 service，移除 Markdown heading、emphasis、list marker、code fence 與 URL 噪音，但不得修改 popup、copy 或 paste 的原文。

Popup、global hotkey 與 shortcut-sequence speech 共用一個 `SpeechCoordinator`。TTS 是單一資源，但取消必須比對 operation ID；舊 popup 關閉、舊 worker 完成或舊 handle 取消，都不得停止或清除新 operation 的 speaking state。

Composable workflow 中，copy/paste/speak 的 fallback text 是目前 displayed step，而非永遠使用最新 step。Back navigation 不呼叫 provider，且 popup selection 仍優先於 displayed step content。
