# Popup Output Actions Contract

Speaker、copy、paste 使用 selection-first：有非空 selection 時使用 selection，否則使用完整 session content。UI 將 selection 放進 typed command，runtime 不讀 Tk widget。

Paste lifecycle：UI 先停用 paste 並隱藏 popup；runtime 關閉 session並交由 worker 執行；output service 保存 clipboard、寫入文字、送出 paste、等待後在 `finally` 恢復 clipboard。失敗不得留下隱藏 session。Delay 必須可注入。

Speech preprocessing 屬於 service，移除 Markdown heading、emphasis、list marker、code fence 與 URL 噪音，但不得修改 popup、copy 或 paste 的原文。
