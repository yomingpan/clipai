# Popup Output Actions Contract

Speaker、copy、paste 使用 selection-first：有非空 selection 時使用 selection，否則使用完整 session content。UI 將 selection 放進 typed command，runtime 不讀 Tk widget。

Paste lifecycle：UI 先停用 paste 並隱藏 popup；runtime 關閉 session並交由 worker 執行；output service 保存 clipboard、寫入文字、送出 paste、等待後在 `finally` 恢復 clipboard。失敗不得留下隱藏 session。Delay 必須可注入。

Speech preprocessing 屬於 service，移除 Markdown heading、emphasis、list marker、code fence 與 URL 噪音，但不得修改 popup、copy 或 paste 的原文。

Popup speech 與 global hotkey speech 是不同入口：popup 使用 `ToggleSpeech(session_id, selected_text)` 並更新 session speaking state；global hotkey 使用 `SpeakSelectionOrClipboard` 與 `SpeechCoordinator`，不建立 popup session。兩者共享 `SpeechOutput` adapter，因此開始新播放前必須取消 global speech，adapter 也必須序列化實際播放器存取。

Composable workflow 中，copy/paste/speak 的 fallback text 是目前 displayed step，而非永遠使用最新 step。Back navigation 不呼叫 provider，且 popup selection 仍優先於 displayed step content。
