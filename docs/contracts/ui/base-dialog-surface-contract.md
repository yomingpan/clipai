# UI Base Dialog Surface Contract

## Intent

Base dialog surface 的核心意圖是讓 ClipAI 的 desktop UI 有一致、快速、可預測的互動外殼。

使用者按下 action 後，如果結果以 dialog 或 popup surface 呈現，視窗必須先快速出現，讓使用者知道系統已收到操作。LLM 內容可以稍後 streaming 或更新，但 UI surface 不能等到模型完成才出現。

這份 contract 是人類意圖、UI 邊界、使用者可見行為、toolkit lifecycle 與測試案例之間的中介層。它同時作為規範文件與 AI coding context。

## Boundary

`ClipAI/ui/base_dialog.py` 屬於 `ui/`，責任是提供 dialog shell、base style 與 lifecycle 接縫。

Base dialog surface 可以做：

- 建立 desktop dialog root。
- 設定 title、geometry、minsize、position 與 base theme。
- 提供內容容器，例如 `main_frame`，讓具體 dialog 填入內容。
- 建立與暴露 `DialogLifecycle`。
- 定義 shared surface vocabulary，例如 base border、header、status line、standard action slots。
- 接收 immutable UI projection 或 toolkit callback，更新純 UI state。

Base dialog surface 不可以做：

- 呼叫 provider。
- 呼叫 platform clipboard、keyboard、notification 或 TTS/STT implementation。
- 執行 services workflow。
- 解析 prompt。
- 選擇 action。
- 執行 action pipeline。
- 決定使用者應該看到哪個業務結果。
- 根據不同 action 任意改變基礎 UI 操作語言。

依賴方向必須符合 `docs/ARCHITECTURE_BOUNDARIES.md`：`ui` 可依賴 `core` typed commands、immutable models 與 ports，但不得 import concrete provider 或 service implementation。跨層使用者操作必須送出 typed semantic command；狀態由 app composition 注入的 presenter port 或 immutable projection 進入 UI。不得建立另一套跨層訊息、Workflow identity 或依賴解析機制。

## Surface Scope

Base dialog surface 規範的是外殼與 lifecycle 接縫，不規範每個具體 dialog 的完整內容。

具體 dialog 或 presenter 負責：

- 填入內容區塊。
- Render services 提供的 typed presentation document；不得在 widget handler 中零散解析 Markdown。
- 更新資料內容。
- 綁定按鈕 command。
- 決定要不要顯示某個 optional action。
- 將使用者操作轉成 typed semantic command；toolkit callback 只負責轉譯 UI intent。

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

目前實作：

- `ClipAI/ui/base_dialog.py` 提供 `CTk` root、`main_frame`、geometry、minsize、position 與 `DialogLifecycle`。
- `ClipAI/ui/result_dialog.py` 的 `ResultDialogPresenter` 使用 `BaseDialog`／`BaseResultSurface`，並負責 Workflow projection、typed output commands、cursor 附近定位、header action bar、border status color 與 completion flash。

## Standard Action Slots

Base dialog surface 應定義穩定的 standard action slots。這些 slots 是 UI vocabulary，不是業務命令。

必備 slots：

- `speaker`：朗讀或停止朗讀目前可見結果。視覺上應使用 speaker icon；正在朗讀時可切換成 stop state。
- `copy`：複製目前可見結果或 selection。視覺上應使用 copy icon。
- `follow_up`：開啟追問輸入。視覺上應使用 pen icon。
- `pin`：固定 surface，避免 focus out 時自動關閉。Pin 必須保留為 base slot。
- `speaker`、`copy`、`paste` 採 selection-first；沒有非空 semantic selection 時才使用 displayed step 的 canonical content。
- Voice Review 進入時預設為「編輯模式」；使用者仍可直接鍵入修改草稿。
  `Ctrl+V` 在編輯與閱讀模式都一律產生外部 Paste intent，不得原生貼入
  Popup。`Ctrl+Enter` 只切換編輯／閱讀呈現；Paste 按鈕在兩種模式都可明確
  觸發外部貼上。
- 在 Voice Review 中，使用者以 `Ctrl+/` 明確開啟 Follow-up 後，下一次
  `Ctrl+Alt+W` 必須以 Follow-up 作為 Voice capture destination；未開啟時才
  繼續 Voice Draft。Presenter 只讀取並回報 Follow-up 可見狀態，runtime 保留
  capture admission 的唯一決策權。
- Paste 必須先隱藏 surface、釋放 focus，再送出 typed command；UI 不得直接操作 clipboard 或 keyboard。
- Paste 的 `pending` 與 terminal acknowledgement 必須以相同 operation ID
  配對；stale acknowledgement 不得改變目前 surface、focus 或 transition。
- `failed` 恢復並聚焦 surface；`cancelled` 恢復但不搶 focus；未 pinned 的一般
  `dispatched_unconfirmed` 保持隱藏並釋放 semantic foreground；未 pinned 的
  Voice Draft 則在 clipboard cleanup 結束後關閉 Popup 與 Workflow；pinned 的
  `dispatched_unconfirmed` 保持可見但不搶 focus；`cleanup_failed` 恢復並顯示
  警告但不搶 focus。Paste 不得顯示 confirmed success。
- Result surface 的 focus state 以邊框作為主要提示。Focused surface 的 footer
  只顯示最近的外部 paste target，不重複標示「已聚焦」；pinned 且 unfocused 時必須說明
  `Ctrl+V` 會由目前外部視窗使用原剪貼簿內容。
- Focus、Voice Draft 模式與 paste target 提示固定置於 popup footer 左下角；
  Voice Review 必須同步說明 `Ctrl+V` 一律外部貼上，以及 `Ctrl+Enter` 將切換
  的呈現模式。model 置於同列
  右下角；兩者必須使用相同字級與顏色，不得占用 header 或 result content
  的閱讀空間，也不得以警示色搶走內容注意力。
- Windows paste target、toolkit focus 與 semantic Foreground Workflow 是三種
  不同身份。Paste target 由 service coordinator 擁有；UI 只呈現 target
  projection 與回報 focus activation candidate。
- 可互動 Popup 初次顯示時必須先完成 layout、提升視窗並將焦點放到 content；
  Voice Listening／Finalizing 保持 non-activating，直到進入 Voice Review 才提出
  初始焦點請求。只有 toolkit 確認焦點位於該 Popup 內，Presenter 才能回報
  `FocusEntered`；焦點呼叫失敗不得被投影成 focused state。
- Toolkit focus 已進入 Popup、但 native foreground 尚未成立時，既有 Popup
  transition owner 必須維持 unfocused projection，並以 generation-bound、有限次
  的重新採樣等待兩軸確認。Popup 內的明確 pointer press 可透過既有
  `DialogLifecycle` 請求 native activation，但不得直接宣告 focused；Paste、owned
  dialog、toolkit focus loss、stale generation 或 retry budget 用盡都必須終止確認。
- Voice Draft 因一般權威 snapshot 更新而替換內容時，surface 必須保存並恢復
  目前 caret，避免非使用者導覽造成插入游標跳動。Voice capture finalized 時則
  使用 revision-bound typed insertion projection，將 selection 收合並把 caret 放在
  本次插入文字的語意終點；UI 不得由前後文字 diff 猜測位置，也不得一律移到全文尾端。
- Paste target 無效、已關閉或無法成為 foreground 時，系統不得向其他視窗
  fallback 或盲送 `Ctrl+V`，必須恢復 surface 並顯示失敗狀態。

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

## Projection / Typed Command Contract

Base dialog surface 透過 immutable projection 或 presenter call 接收 UI-safe
state change。Toolkit focus、activation、geometry 與 close events 可以在 adapter
內解讀，但跨層輸入必須轉成 typed semantic command，不得廣播 global event。

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

Base dialog surface 對 projection 的反應只能改變 UI state，例如文字、enabled state、focus、border color、button state、visibility。

## Current Implementation Notes

目前 `ClipAI/ui/base_dialog.py` 承擔通用 dialog shell 與 lifecycle 接線；
`ClipAI/ui/result_dialog.py` 的 `ResultDialogPresenter` 已組合該 surface，並包含：

- result surface 快速顯示。
- speaker、copy、pin 與其他 action buttons。
- follow-up input。
- TTS state 對 speaker button 的 UI state mapping。
- success/error border flash。
- focus out close 與 pin 行為。

後續 UI 調整必須維持這個 composition，不得讓 BaseDialog 直接承擔 provider、clipboard、TTS 或 Action Workflow。

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

Base dialog surface 只呈現狀態、接收操作，並把操作轉成 typed semantic command。

## Testing Links

已存在測試參考：

- `tests/ui/test_base_dialog.py`
- `tests/ui/test_result_dialog.py`

目前覆蓋：

- TTS phase 可轉成 speaker button UI state。
- loading state formatting。
- popup action handler 優先使用 selection，再 fallback full output。
- copy / archive handler 可被 fake clipboard 與 fake archive service 測試。
- toggle speak 可透過 fake TTS service 測試。
- follow-up toggle 會插入到 meta row 前並 focus entry。
- Workflow close、stale acknowledgement 與 lifecycle cleanup 不會更新已銷毀的 surface。

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
- Dialog 關閉後的 late projection 不更新 destroyed widget，也不 crash。

## Decision Log

- 2026-06-07：建立 UI base dialog surface contract。
- Base dialog 規範外殼與 lifecycle 接縫；具體內容與資料更新由各 dialog 或 presenter 負責。
- `DialogLifecycle` 是 BaseDialog contract 的一部分。
- BaseDialog 必須嚴格禁止跨層依賴，不得碰 provider、platform、services、prompt、action pipeline 或 clipboard。
- Standard action slots 必須包含 `speaker`、`copy`、`follow_up` 與 `pin`。
- `archive`、`overflow`、`delete`、`deep`、`refine` 先列為 optional slots。
- `follow_up` 視覺語言是 pen icon。
- 所有承載 LLM result 的 surface 都必須在 result finalized 後閃爍 success green `1000ms`。
- `ResultDialogPresenter` 已使用 `BaseDialog`／`BaseResultSurface`；後續不得重新建立平行 popup shell。
