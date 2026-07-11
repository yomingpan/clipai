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

## Done

- Product philosophy documented.
- Architecture boundaries documented.
- Testing strategy documented.
- Base dialog surface prototype.
- Hotkey dispatcher tests.
- Phase 3 vertical slice.
- Phase 4 Gemini provider MVP.
