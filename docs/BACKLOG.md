# ClipAI Next-gen Backlog

## 2026-07-11 Interaction Contract Decisions

- Result popup 永遠 topmost；pin 只控制 focus out 留存，且 pin/unpin 必須有明確 icon、tooltip 與 active state。
- Speaker、copy、paste 統一 selection-first；paste 隱藏 popup 後貼回原應用並恢復原 clipboard。
- TTS 使用獨立 speech text preprocessing，避免朗讀 Markdown 符號。
- LLM 格式由集中式 output profile 管理，action 與 press variant 只引用 profile ID。
- Tray 使用雙斜線 status icon；memory 黃點只預留 contract，等待真實 memory service。
- Every accepted user action needs immediate visible feedback. Active workflows reflect their real lifecycle; commands without acknowledgment show only a requested state.
- Tray status is driven by external LLM/TTS call boundaries, not by general session snapshots. This prevents duplicate success lights from speech cleanup or popup rendering.
- Copy and Archive need a future typed acknowledgment if confirmed-success icons are required instead of requested feedback.
- Concurrent API work is projected through an operation-identity coordinator; feature code must not add local tray precedence rules.

## 2026-07-11 Reliability Foundation

- Windows CI validates Python 3.10-3.13 with constrained dependencies; release tags must match project metadata.
- Config catalogs use schema version 1 with in-memory legacy migration.
- Provider secrets are resolved only in the composition root; missing active credentials are non-fatal readiness issues.
- Concurrent LLM/TTS status is owned by `OperationLifecycleCoordinator`.
- Tray can request a redacted diagnostics archive through a typed command.

本文件整理目前開發過程中浮現的需求。下次繼續開發時，先從這份 backlog 抽 item，再規劃當期 milestone 與優先順序。

## Current State

- Phase 3 vertical slice 已完成：
  - hotkey
  - clipboard input
  - action resolve
  - dialog loading/result
  - fake provider
  - copy/close
- Phase 4 Gemini provider MVP 已完成：
  - `provider.provider: gemini`
  - Gemini non-streaming `generateContent`
  - provider error 顯示到 dialog
  - fake provider fallback
- 目前產品已可跑：
  - clipboard: `appetizer`
  - hotkey: `Ctrl+Alt+8`
  - output: Gemini 真實回覆顯示在 dialog

## Priority 1: Immediate User Feedback

目標：使用者按下快捷鍵後，ClipAI 要立刻有可見反應，建立掌控感與信任感。

目前觀察到的問題：

- 視窗太慢才出現。
- 使用者按下 hotkey 後，不知道 ClipAI 是否有收到操作。
- 如果 AI request 在背景執行太久，使用者會感覺系統在背後偷偷做事。
- 缺少「目前正在做什麼」的透明狀態。

需求：

- hotkey 觸發後，dialog 應立即出現，不要等 provider 回應。
- dialog 先顯示清楚 loading/status，例如：
  - `Reading clipboard...`
  - `Preparing English Companion...`
  - `Asking Gemini...`
  - `Rendering result...`
- provider request 執行時，使用者要看得到目前正在處理。
- error 也要在同一個 dialog 顯示，不要靜默失敗。

成功標準：

- 按下快捷鍵後，使用者能在極短時間內看到視窗或狀態變化。
- 使用者知道 ClipAI 已收到 hotkey。
- 使用者知道目前卡在哪個階段。
- 即使 provider 很慢，使用者仍感覺自己掌控流程。

## Priority 2: Click Outside To Close

目標：dialog 出現後，如果使用者點擊非 ClipAI UI 的其他區域，視窗應自動關閉，符合輕量 popup 的使用直覺。

目前觀察到的問題：

- dialog 目前需要手動按 close。
- 使用者如果只是想快速看一下結果，額外關閉動作會增加摩擦。
- 小工具型 UI 應該像 popup 一樣，不打擾使用者回到原本工作流。

需求：

- dialog 開啟後，偵測使用者點擊 ClipAI 視窗外部。
- 點擊外部時自動 close dialog。
- 點擊 dialog 內部、選取文字、按 copy/follow-up/button 不應關閉。
- pinned 狀態應保留視窗，不因外部點擊關閉。
- 後續若有 follow-up input，輸入中不應被誤判關閉。

成功標準：

- 使用者按 hotkey 看完結果後，點擊其他 app/桌面區域，dialog 自動關閉。
- 使用者點擊 dialog 內操作時不會誤關閉。
- pinned dialog 不會因外部點擊關閉。
- 這個行為可用 unit 或 integration seam 驗證，不把 OS mouse listener 直接塞進 service。

## Priority 3: Provider Runtime Hardening

目標：讓真實 Gemini 使用時比較穩。

需求：

- Gemini request timeout 可從 config 設定。
- Provider error message 縮短，避免整段 API response 塞進 dialog。
- Missing API key 時，啟動或第一次 hotkey 觸發時給清楚錯誤。
- 保留 `provider.provider: fake` 作為本機無網路 smoke test。

成功標準：

- API key 缺失、網路錯誤、HTTP error 都能被使用者理解。
- 測試不需要打真實網路。

## Priority 4: Result Presentation Cleanup

目標：讓 Gemini 回來的內容變成適合小視窗閱讀的產品輸出。這是後續體驗優化，不是下一步最優先。

目前觀察到的問題：

- 模型會重述 input、role、goal、constraints。
- 內容有重複段落。
- Markdown bullet 太多，不適合小 dialog。
- dialog 目前只是把純文字塞進 textbox，沒有做結構化呈現。

需求：

- 收斂 `English Companion` prompt，禁止模型重述任務與 constraints。
- 加一層 result postprocess，移除明顯多餘段落，例如：
  - `Input:`
  - `Role:`
  - `Goal:`
  - `Constraints:`
  - `Structure:`
- English Companion short press 固定收斂成 4 行：

```text
appetizer
餐前的小點心或開胃菜
Let's order some appetizers first.
Synonym: starter, hors d'oeuvre
```

成功標準：

- 使用者複製 `appetizer` 後按 hotkey，只看到最小有用學習單位。
- 不出現 prompt/debug/任務說明類內容。
- 內容少於 5 個主要認知點。

## Priority 5: Dialog Rendering Quality

目標：讓 UI 呈現更像產品，而不是 raw text viewer。

需求：

- `BaseResultSurface` 支援簡單的 section/line rendering。
- English Companion short result 可用固定 layout 顯示：
  - word/phrase
  - meaning
  - example
  - synonyms
- copy button 複製乾淨結果，不複製 UI/debug metadata。
- error state 與 normal result state 視覺上要明確不同。

成功標準：

- 同一份 result 在 dialog 內更容易掃讀。
- 文字不需要使用者自行解析 Markdown 結構。

## Priority 6: Input Scope Expansion

目標：從 clipboard-only 擴展到更貼近真實使用。

需求：

- 支援 selection 優先，clipboard fallback。
- 釐清 selection capture 是否由 platform 層處理。
- 不破壞目前 clipboard-only vertical slice。

成功標準：

- 使用者選取文字後按 hotkey，可直接分析選取內容。
- 沒有 selection 時仍可用 clipboard。

## Priority 7: Output Actions

目標：讓結果可以被拿去用，而不只被看。

需求：

- copy result 已有，需維持。
- paste/replace selected text。
- archive result。
- speaker/TTS result。
- action button enabled/disabled state 依功能 readiness 控制。

成功標準：

- 每個 output action 都可獨立測試。
- UI button 不會露出尚未實作但可點擊的假功能。

## Priority 8: Follow-up Loop

目標：讓使用者可以基於目前結果追問。

需求：

- follow-up input row 接回 service workflow。
- 保留上一輪 input/result context。
- long/short action 的 follow-up 行為要明確。
- follow-up 中 provider error 不應關閉原 dialog。

成功標準：

- 使用者可以在同一個 dialog 追問一次以上。
- close 後 session cleanup 正確。

## Priority 9: Desktop Runtime Productization

目標：從可跑的 script 變成可長期使用的桌面 app。

需求：

- tray。
- startup/shutdown lifecycle。
- logging。
- settings/config validation。
- packaging/run script 修正。
- `.venv` Python 啟動問題需要處理。

成功標準：

- 使用者可以用正常入口啟動，不需要手動拼 `PYTHONPATH`。
- runtime stop 後 hotkey listener 會釋放。

## Priority 10: Image Input via Screenshot Hotkey

目標：讓使用者可以在現有快捷鍵流程中，直接輸入圖片內容，例如截圖後立即分析。

目前觀察到的問題：

- 目前僅支援 clipboard text input，缺少 image input。
- 使用者在工作流中常常需要先截圖再切換到其他工具。
- 以 screenshot 進入的資訊，對於視覺理解或 UI/設計/錯誤訊息等場景很有價值。

需求：

- 支援 screenshot capture flow，使用者可選取區域或全螢幕截圖。
- 截圖後可透過 hotkey 直接送入流程。
- image input 需要在 platform 層抽象 capture 能力，並由 services/providers 進行 multimodal 處理。
- 如 provider 無法處理 image，需有清楚 fallback / error。

成功標準：

- 使用者可在不離開當前工作流下，截圖並送入 ClipAI。
- 截圖內容可被正確辨識與分析。
- 既有 text-only flow 不受影響。

## Priority 11: Guided Hotkey Onboarding

目標：讓新使用者知道如何使用快捷鍵，並提升第一次使用的成功率。

目前觀察到的問題：

- 使用者可能不知道 hotkey 是什麼、如何啟動、如何觸發。
- 功能本身很實用，但缺乏可見的引導與學習曲線。

需求：

- 需設計一套使用者引導機制，包含首次啟動提示、熱鍵介紹與可操作範例。
- 引導設計需要深入討論，評估是否以 overlay、toast、settings page、或首次使用動畫等方式呈現。
- 引導內容必須在不打斷使用者主要工作流的前提下提供。

成功標準：

- 新使用者能在短時間內理解「如何使用 ClipAI」。
- 引導機制不會造成過多干擾。
- 設計討論完成後，可落成可測試的 onboarding flow。

## Priority 12: Language-aware Speech Output

目標：讓 speak 的語音輸出能根據內容語言選擇更合適的語音。

目前觀察到的問題：

- 目前 TTS 可能無法自然區分中英文內容。
- 使用者希望英文內容使用較自然的英文語音，中文內容使用中文語音。

需求：

- 依內容語言自動選擇語音，英文使用英語語音，中文使用中文語音。
- 這個行為可作為未來的 voice profile / language profile 設計之一。
- 若有更好的方案，應在實作前研議。

成功標準：

- 英文內容朗讀時使用英文語音。
- 中文內容朗讀時使用中文語音。
- 使用者可感受到語音更自然，減少語感不一致。

## Priority 13: Voice Input via Speech-to-Text

目標：讓使用者可以直接用語音輸入，降低打字成本並提升輸入準確度。

目前觀察到的問題：

- 文字輸入仍是摩擦點，尤其在切換應用或快速記錄時。
- 使用者希望更自然的輸入方式。

需求：

- 可整合語音輸入流程，例如利用 ChatGPT 的 speech-to-text / transcription 能力。
- 語音轉文字後可直接進入 ClipAI 的輸入流程，提升輸入精準度。
- 需評估 privacy、latency、accuracy 與 fallback strategy。

成功標準：

- 使用者可透過語音輸入建立內容。
- 轉文字結果足夠精準，減少手動修正。
- 語音輸入與現有 text input flow 可共存。

## Core Direction: Composable Shortcut Chains

這是 ClipAI 未來的核心產品能力，不是單一快捷鍵功能。ClipAI 應讓使用者把目前結果直接交給下一個 shortcut，形成低摩擦、可連續組合的內容處理鏈。

核心精神：

- Popup 不只是輸出終點，也能成為下一個 action 的輸入。
- Shortcut 不只啟動獨立功能，也能接續前一步結果。
- 使用者應能用短按、長按與後續 shortcut 表達處理強度和輸出方式。
- 每一步都必須有明確 input、operation lifecycle、結果 ownership 與可見 feedback。
- 不得以 Runtime action ID 特判、global event、UI widget 直讀或 platform 業務狀態機實作。

### Capability A: Popup Result Chaining

使用情境：

- 新增「簡短內容」shortcut，例如 `Ctrl+Alt+X`。
- 短按：保持原意，將內容縮短約 80%。
- 長按：保持原意，縮短成最精煉、仍可理解的表達。
- 沒有 active popup 時，使用既有 selection-first、clipboard fallback。
- 有 active popup 時，以目前 foreground popup 已完成的可見結果作為輸入，而不是重新讀 selection 或 clipboard。
- 處理結果延續在同一個使用者工作流中，讓「口語化 → 縮短 → 再加工」形成可理解的鏈。

產品規則：

- 只能使用已完成且仍有效的 session result；loading、failed、cancelled 或 closed session 不得成為 chain input。
- 觸發瞬間先擷取 immutable input snapshot，再取消或更新舊工作，避免 session lifecycle race。
- 使用者必須看到新一步已開始、成功或失敗；舊內容在新結果完成前不得無預警消失。
- 新一步失敗時應保留上一個有效結果，讓使用者可重試或繼續使用。
- 必須定義同一 popup 更新、歷史返回與 pinned session 的行為，不能用「session collection 非空」推測目標。

需要的架構能力：

- Typed input target，例如 `external_context`、`foreground_result` 與明確的 fallback policy。
- `ForegroundSessionReader` 或等價 read-only port，只暴露 immutable session result，不讓 service 讀 UI widget。
- Action invocation 必須攜帶 resolved input snapshot 或 target descriptor；Runtime 不以 action ID 決定來源。
- Session lineage metadata，例如 parent session / step ID，支援追蹤鏈條、失敗回復與未來歷史功能。
- Popup presenter 應呈現同一 workflow 的 revision/step，而不是讓多個 session controller 爭奪同一視窗。

成功標準：

- 使用者可連續執行「口語化 → 短按縮短 → 長按極簡」，每一步都以前一步結果為輸入。
- Provider 失敗、快速重觸或舊工作晚完成時，不會覆蓋較新的結果。
- 沒有 popup 時仍維持 selection-first、clipboard fallback。
- Popup chaining 不讓 UI、platform、provider 跨越既有架構邊界。

### Capability B: Shortcut Sequence Composition

使用情境：

- 使用者長按 `Ctrl+Alt+Q`，進入「處理後直接朗讀」的短暫等待狀態。
- 接著按下另一個 action shortcut，例如 `Ctrl+Alt+6` 代表口語化表達。
- ClipAI 取得來源內容，先執行 `Ctrl+Alt+6` 對應的 action，再將結果直接送入 TTS。
- 整個流程不開啟 popup，但仍提供 processing、speaking、success 或 failure feedback。

產品規則：

- Sequence 必須有明確 timeout；逾時後取消等待狀態，不得永久攔截後續 shortcut。
- 必須有清楚的 pending feedback，讓使用者知道系統正在等待下一個 shortcut。
- 不支援的第二鍵、重複 prefix、Escape/shutdown 與新 sequence 都必須有確定的取消規則。
- 第二個 shortcut 的 short/long press 語意必須保留，不能因 sequence 而退化。
- Direct speech pipeline 若失敗，不得建立空 popup或播放舊內容。

需要的架構能力：

- Platform hotkey listener 繼續只輸出 atomic `shortcut_id + press_type`，不負責 sequence 語意。
- 在 services/app 邊界新增 `ShortcutSequenceCoordinator` 狀態機，負責 idle、awaiting-next、executing、cancelled/expired。
- Sequence resolution 產生 typed composite invocation，例如「執行 action，將結果 route 至 speech」。
- Action pipeline 的 result destination 必須由 typed output route 表達，例如 `popup` 或 `speech`；不得用 action ID 或 UI branch 判斷。
- Composite operation 需要 parent operation ID，並正確串接 provider 與 TTS lifecycle；provider 成功不等於整條 sequence 成功。

成功標準：

- `Ctrl+Alt+Q` 長按後接 action shortcut，可在不開 popup 的情況下朗讀轉換結果。
- Sequence timeout、取消、錯誤與快速重觸行為可單元測試且可預測。
- Provider 與 TTS 任一步失敗時，整體狀態正確，不顯示假成功。
- 未參與 sequence 的既有 shortcuts 行為完全不變。

### Recommended Architecture Order

1. 先建立 typed `InputTarget` 與 foreground result snapshot contract，完成 popup result chaining。
2. 將 action 執行結果與 presentation 拆開，建立 typed `ResultRoute`（popup / speech）。
3. 再建立 `ShortcutSequenceCoordinator`，組合既有 action invocation 與 result route。
4. 最後加入 sequence pending UI、timeout、取消與 workflow history。

不建議現在只為範例快捷鍵新增 action ID 特判、把 popup content 寫回 clipboard、讓 hotkey listener 保存 sequence state，或讓 UI 直接呼叫 provider/TTS。這些作法會破壞 session ownership，也會讓未來每個 chain 增加新的耦合。

## Done

- Product philosophy documented.
- Architecture boundaries documented.
- Testing strategy documented.
- Base dialog surface prototype.
- Hotkey dispatcher tests.
- Phase 3 vertical slice.
- Phase 4 Gemini provider MVP.
