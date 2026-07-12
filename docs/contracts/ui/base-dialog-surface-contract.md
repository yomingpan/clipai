# UI Base Dialog Surface Contract

## Intent

Base dialog surface 的核心意圖是讓 ClipAI 的 desktop UI 有一致、快速、可預測的互動外殼。

使用者按下 action 後，如果結果以 dialog 或 popup surface 呈現，視窗必須先快速出現，讓使用者知道系統已收到操作。LLM 內容可以稍後 streaming 或更新，但 UI surface 不能等到模型完成才出現。

這份 contract 是人類意圖、UI 邊界、使用者可見行為、event lifecycle 與測試案例之間的中介層。它同時作為規範文件與 AI coding context。

## Boundary

`clipai/ui/base_dialog.py` 屬於 `ui/`，責任是提供 dialog shell、base style 與 lifecycle 接縫。

Base dialog surface 可以做：

- 建立 desktop dialog root。
- 設定 title、geometry、minsize、position 與 base theme。
- 提供內容容器，例如 `main_frame`，讓具體 dialog 填入內容。
- 建立與暴露 `DialogLifecycle`。
- 定義 shared surface vocabulary，例如 base border、header、status line、standard action slots。
- 接收 UI-safe event 或 presenter callback，更新純 UI state。

Base dialog surface 不可以做：

- 呼叫 provider。
- 呼叫 platform clipboard、keyboard、notification 或 TTS/STT implementation。
- 執行 services workflow。
- 解析 prompt。
- 選擇 action。
- 執行 action pipeline。
- 決定使用者應該看到哪個業務結果。
- 根據不同 action 任意改變基礎 UI 操作語言。

依賴方向必須符合 `docs/ARCHITECTURE_BOUNDARIES.md`：`ui` 可依賴 `core` event contract 與 service session model，但不得 import concrete provider。需要服務時，必須透過 callback、gateway、event 或 app composition 注入。

## Surface Scope

Base dialog surface 規範的是外殼與 lifecycle 接縫，不規範每個具體 dialog 的完整內容。

具體 dialog 或 presenter 負責：

- 填入內容區塊。
- Render services 提供的 typed presentation document；不得在 widget handler 中零散解析 Markdown。
- 更新資料內容。
- 綁定按鈕 command。
- 決定要不要顯示某個 optional action。
- 將使用者操作轉成 callback 或 event。

Base dialog surface 負責：

- 提供一致的視窗行為。
- 提供一致的 base style。
- 提供一致的標準按鈕 slot 語言。
- 提供一致的 completion status language。
- 清理 lifecycle 中的 scheduled jobs 與 event subscriptions。

## Lifecycle Contract

`DialogLifecycle` 是 BaseDialog contract 的一部分。

Base dialog surface 必須提供 lifecycle 抽象，讓具體 dialog 不需要各自重新實作開啟、關閉、focus、scheduled jobs 與 event subscription cleanup。

Lifecycle 必須支援：

- `run_dialog()` 或等價入口，用於啟動 dialog mainloop。
- `close()`，負責停止 mainloop、destroy root、取消 scheduled jobs、unsubscribe events。
- `schedule(delay_ms, callback)`，讓 UI 延遲行為可被追蹤並在 close 時取消。
- close on Escape。
- close on focus out。
- force focus 到 root 或指定 widget。
- event subscription tracking。

Lifecycle cleanup 是穩定性要求，不是附加功能。Dialog 關閉後，不得留下會更新已 destroyed widget 的 scheduled callback 或 event subscription。

## Base Style

Base dialog surface 必須提供一致的視覺語言。

基礎視覺規範：

- 視窗使用 restrained、清楚、低干擾的工作型 UI。
- 內容容器應有清楚邊界，但不得用過度裝飾搶走內容注意力。
- 基礎 border 是狀態語言，不只是裝飾。
- Header 應顯示目前 surface 的明確標題。
- 尺寸必須有合理 minsize，避免內容在小視窗中擠壓到不可用。
- Position 支援 center 與 cursor 附近定位。
- 色彩必須服務狀態辨識，不應製造驚喜或分散注意力。
- Result popup 預設 always-on-top；pin 只控制 focus out 後是否保留，不改變 topmost。
- Pin 與 unpin 必須使用固定 icon、tooltip 與 active style，snapshot 更新時同步校正視覺狀態。
- Header 的非互動區域皆可拖曳，包含 model label；close、pin 與其他 control 不得被 drag binding 攔截。

目前實作參考：

- `clipai/ui/base_dialog.py` 提供 `CTk` root、`main_frame`、geometry、minsize、position 與 `DialogLifecycle`。
- `clipai/ui/popup_presenter.py` 提供 result surface 的實作參考，包含 cursor 附近定位、header action bar、border status color 與 completion flash。

## Standard Action Slots

Base dialog surface 應定義穩定的 standard action slots。這些 slots 是 UI vocabulary，不是業務命令。

必備 slots：

- `speaker`：朗讀或停止朗讀目前可見結果。視覺上應使用 speaker icon；正在朗讀時可切換成 stop state。
- `copy`：複製目前可見結果或 selection。視覺上應使用 copy icon。
- `follow_up`：開啟追問輸入。視覺上應使用 pen icon。
- `pin`：固定 surface，避免 focus out 時自動關閉。Pin 必須保留為 base slot。
- `speaker`、`copy`、`paste` 採 selection-first；沒有非空 selection 時才使用完整 result。
- Paste 必須先隱藏 surface、釋放 focus，再送出 typed command；UI 不得直接操作 clipboard 或 keyboard。

Optional slots：

- `archive`
- `overflow`
- `delete`
- `deep`
- `refine`

Result popup 預設只顯示 `speaker`、`copy`、`follow_up`；`paste` 與 `archive` 放入右側 overflow disclosure。Back 只在 workflow history 可返回時顯示。

Popup geometry 由 injectable display metrics 與集中式 logical layout policy 計算；UI 不得散落 DPI、monitor work area 或 action-specific pixel branch。

Slot command 綁定規則：

- Base dialog surface 可以建立 slot、設定樣式、tooltip、enabled/disabled state 與 success/error pulse。
- Every accepted user command must produce immediate visible feedback. Long-running actions retain an active state for their real lifecycle; fire-and-forget commands show a short requested/pressed state.
- A requested state must not claim success. Copy or Archive may show `requested` immediately, but may show `copied` or `archived` only after an explicit typed acknowledgment exists.
- Speaker changes to its Stop icon immediately when speech work is accepted and remains active until the supervised speech task ends or is stopped.
- 具體 presenter 或 dialog 才能把 slot 綁到 TTS、clipboard、follow-up workflow、archive 或其他服務。
- Base dialog surface 不得直接 import platform clipboard、TTS service、archive service 或 action runner。

## Completion Status Language

所有承載 LLM result 的 dialog surface 都必須支援 completion status language。

行為規範：

- Result surface 必須先快速顯示 loading 或空狀態，不能等 LLM 完成後才出現。
- Streaming 或 partial content 可逐步更新內容區。
- 當 LLM result finalized 時，surface border 或 status line 必須閃爍 success green `1000ms`。
- Success flash 結束後，border 或 status line 回到 default color。
- Error 狀態可使用 error red，且 duration 可長於 success flash。
- 非 LLM result dialog，例如 hotkey guide 或 memory list，不強制套用 completion flash。

Success green 是「內容已完成，可以閱讀」的訊號。它不能代表 provider 成功率、模型品質或使用者是否應該採納內容。

## Event / Callback Contract

Base dialog surface 可以透過 event 或 callback 接收 UI-safe state change。

允許的訊號類型：

- content loading started。
- content chunk appended。
- result finalized。
- result failed。
- TTS state changed。
- follow-up availability changed。
- close requested。

禁止的訊號處理：

- 在 BaseDialog 中直接呼叫 provider。
- 在 BaseDialog 中直接呼叫 services workflow。
- 在 BaseDialog 中直接讀寫 clipboard。
- 在 BaseDialog 中直接決定 action variant 或 prompt。

Base dialog surface 的 event 反應只能改變 UI state，例如文字、enabled state、focus、border color、button state、visibility。

## Current Implementation Notes

目前 `clipai/ui/base_dialog.py` 已承擔通用 dialog shell 與 lifecycle 接線。

目前 `clipai/ui/popup_presenter.py` 尚未收斂到 `BaseDialog`，但它是重要參考實作，因為它已包含：

- result surface 快速顯示。
- speaker、copy、pin 與其他 action buttons。
- follow-up input。
- TTS state 對 speaker button 的 UI state mapping。
- success/error border flash。
- focus out close 與 pin 行為。

未來若重構 popup presenter，應朝本 contract 收斂，而不是讓 BaseDialog 直接承擔 provider、clipboard、TTS 或 action workflow。

## Forbidden Decisions

Base dialog surface 不得做以下決策：

- 哪個 provider 被呼叫。
- 哪個 model 被使用。
- 哪個 prompt 被送出。
- 哪個 action variant 被套用。
- result 是否要寫入 clipboard。
- result 是否要 archive。
- follow-up 次數政策。
- LLM result 的業務解讀。
- 使用者是否應該採納或執行結果。

Base dialog surface 只呈現狀態、接收操作，並把操作轉成 callback 或 event。

## Testing Links

已存在測試參考：

- `tests/ui/test_popup_presenter.py`

目前覆蓋：

- TTS phase 可轉成 speaker button UI state。
- loading state formatting。
- popup action handler 優先使用 selection，再 fallback full output。
- copy / archive handler 可被 fake clipboard 與 fake archive service 測試。
- toggle speak 可透過 fake TTS service 測試。
- follow-up toggle 會插入到 meta row 前並 focus entry。
- popup presenter dispose 會 unsubscribe TTS subscription。

應補 unit / sims 測試：

- BaseDialog 建立 root、main_frame 與 lifecycle。
- BaseDialog position center / cursor fallback。
- DialogLifecycle close 會 cancel scheduled jobs。
- DialogLifecycle close 會 unsubscribe event subscriptions。
- standard action slots 的名稱、順序、tooltip 與 enabled/disabled state 穩定。
- LLM result finalized 時 success green flash `1000ms` 後回 default color。
- pin enabled 時 focus out 不關閉；pin disabled 時 focus out 可關閉。
- follow-up slot 使用 pen icon，且由 presenter 綁定 callback，不由 BaseDialog 執行 workflow。
- BaseDialog 不 import provider、platform clipboard、services action runner。

## Manual / Integration Scenarios

這些情境應在真實 app 啟動後手動或以 integration test 驗證；不要求本 contract 建立時立刻全部自動化。

- 按下 hotkey 後 result surface 立即出現，即使 LLM 內容尚未完成。
- Streaming 中內容可更新，視窗不閃爍、不重建、不搶走不必要焦點。
- LLM 完成後 border/status line 綠色閃爍 `1000ms`，再回 default。
- Speaker button 可切換 speak / stop state。
- Copy button 對 selection 與 full result 行為符合預期。
- Follow-up pen button 開啟追問輸入，並受回合限制控制。
- Pin 開啟後 focus out 不關閉 surface。
- Dialog 關閉後不再收到 event update，不 crash。

## Decision Log

- 2026-06-07：建立 UI base dialog surface contract。
- Base dialog 規範外殼與 lifecycle 接縫；具體內容與資料更新由各 dialog 或 presenter 負責。
- `DialogLifecycle` 是 BaseDialog contract 的一部分。
- BaseDialog 必須嚴格禁止跨層依賴，不得碰 provider、platform、services、prompt、action pipeline 或 clipboard。
- Standard action slots 必須包含 `speaker`、`copy`、`follow_up` 與 `pin`。
- `archive`、`overflow`、`delete`、`deep`、`refine` 先列為 optional slots。
- `follow_up` 視覺語言是 pen icon。
- 所有承載 LLM result 的 surface 都必須在 result finalized 後閃爍 success green `1000ms`。
- `PopupPresenter` 是目前尚未收斂到 BaseDialog surface 的重要參考實作。
