# ClipAI Next-gen Backlog

## Completed 2026-07-12: Context Actions, Selection Priority, And Popup Readability

Status: implemented across the latest five commits; `07a1bad` is the merge of the popup UI work in `6b40aee`, and `8cc8b13` is the preceding backlog update.

- Context action configuration is restored and covered by config tests:
  - `Ctrl+Alt+1` through `Ctrl+Alt+0`, plus `Ctrl+Alt+E`, now map to eleven typed actions for translation, idea naming, essence analysis, pyramid structuring, friendly explanation, article structure, English learning, reflective questioning, critical thinking, and keyword extraction.
  - Every context action uses selection-or-clipboard input, supports the existing multimodal path, and declares its prompt, output profile, and popup destination in configuration rather than runtime action-ID branches.
  - English Companion now teaches one practical expression through Word or Phrase, Meaning, Context, and Example sections, with a synonym section only when useful.
- Action input priority now reflects the user's explicit selection at trigger time:
  - Valid selected text takes precedence over a clipboard image or clipboard text.
  - Without a valid selection, a clipboard image takes precedence over clipboard text.
  - Selection capture preserves both clipboard text and image and restores them only when the clipboard sequence still belongs to that capture, preventing an older operation from overwriting newer clipboard changes.
- Popup reading and interaction details are improved:
  - The reading-first baseline is now `400 × 320` logical units with more distinct heading typography, spacing, and color hierarchy.
  - Tooltip windows remain above the always-on-top popup without taking focus.
  - Snapshot changes that do not affect content no longer rewrite the textbox or reset the user's scroll position.

Commits: `bfea2c9`, `07a1bad` (merge of `6b40aee`), `16daa94`, `8cc8b13`.

## Completed 2026-07-12: Shortcut Composition, Multimodal Clipboard, And Output Acknowledgment

Status: implemented and manually accepted on branch `codex/shortcut-screenshot-ack`.

- Shortcut sequence composition is complete:
  - Long-press `Ctrl+Alt+Q`, release `Q`, then enter an existing full action shortcut within one second.
  - The composed action preserves short/long semantics, runs without a popup, and speaks the result directly.
  - Waiting, provider, TTS, success, cancellation, timeout, invalid-key, replacement, and late-completion lifecycles use typed operation identity.
  - Sequence failures remain visible on the tray; `Show Last Error` replays the reason and recommendation through a Windows notification.
- Multimodal clipboard input is complete with revised scope:
  - ClipAI does not implement region or full-screen capture; users continue using their preferred screenshot tool.
  - Text explicitly selected when the action is triggered takes precedence; when selection is unavailable, a readable clipboard image takes precedence over clipboard text.
  - OpenAI, Gemini, and Anthropic adapters serialize the shared typed image contract into native multimodal payloads.
  - Invalid, oversized, or model-incompatible images fail safely without text fallback, automatic model switching, or image data in diagnostics.
- Copy and Archive confirmed-success feedback is complete:
  - Both intents carry explicit semantic text and operation identity; popup selection takes precedence over canonical result content.
  - The UI shows a check only after a typed success acknowledgment and shows an error state after failure.
  - Collapsed Archive overflow shows `已封存` for one second; Archive does not close the popup.
  - Focused popup shortcuts are `Ctrl+Q` Speak, `Ctrl+C` Copy, and `Ctrl+S` Archive.
- Windows popup task-switcher behavior is complete:
  - Result popups use the Windows tool-window style and are hidden from both the taskbar and Alt+Tab.
  - The ClipAI tray icon remains the persistent application surface.
- Verification: compile succeeded and the complete unit/architecture suite reports `185 passed`. The repository currently has no tests marked `integration`; Windows behavior was accepted through manual verification.

Commits: `69637e6`, `fe7eebe`, `c1be04c`, `696dc15`.

## 2026-07-12 Popup Reading Experience And Interaction Requirements

今天確認的核心方向：Popup 的首要任務是讓使用者快速理解內容。內容結構、視窗尺寸、文字呈現與按鈕數量都必須降低認知負荷；功能不能只是存在，也必須在真正需要時才出現。

### Implementation Status (2026-07-12)

已完成：

- `Ctrl+Alt+Q` 每次觸發建立獨立 speech/capture identity，序列化 selection capture 與 clipboard restore，舊 operation 不得污染新 operation。
- Popup lifecycle、provider completion、Back、pin 與 focus 不會推導 speech intent；只有 typed speech commands 可啟動 TTS。
- 首次 popup 在 view registration 後建立 focus lifecycle；click-outside 只送出 typed close command，pin 與內部互動保持有效。
- 建立 typed immutable Markdown presentation model，支援 heading、list、bold、italic、paragraph 與 safe plain-text fallback；canonical content 不受 UI styling 污染。
- Global output prompt 統一限制最多四個核心區塊，result diagnostics 會偵測超量 heading、nested list 與缺少 required markers。
- Popup actions 預設顯示 Speak、Copy、Follow-up；Paste、Archive 收納至 overflow，Back 僅在 workflow history 可返回時顯示。
- Popup 採固定 `400 × 320` logical units，內容量不再改變視窗比例，長內容由 scrolling 承擔。
- DPI-aware geometry 使用 injectable display metrics 與 monitor work area；CustomTkinter window scaling 與 raw Tk canvas scaling 分開處理，避免二次縮放或內容區裁切。
- Completion border 只對新的 workflow step 閃綠一次並回到 ready 色；一般 snapshot revision 不會重啟或延長 success state。
- English Companion 的 word、meaning、example、synonym 保留原始換行，避免 compact output 被合併成單行。

目前驗證：

- Compile、targeted、architecture 與完整 unit suite 通過；完整 suite 為 `176 passed`。
- 舒適尺寸基準已調整為 `400 × 320` logical units；各縮放比例的 physical size 與多螢幕體驗仍待 manual matrix 驗證。
- 尚待人工完成 Windows 100%、125%、150%、175%、200% scaling、多螢幕、首次 click-outside 與快速連續 selection/TTS smoke matrix。

### Bug: Ctrl+Alt+Q Repeated Selection Speech

問題：

- 第一次選取外部文字後按 `Ctrl+Alt+Q`，能正確朗讀 selection。
- 第二次選取另一段文字並再次觸發時，可能忽略新的 selection，改讀舊內容或 clipboard。
- 每次獨立觸發都應重新取得使用者當下的 selection，不能沿用上一次 capture 結果或殘留狀態。

需求：

- 修復 `Ctrl+Alt+Q` 重複觸發時無法讀取最新選取文字的問題。
- 每次 trigger 必須建立新的 selection capture lifecycle 與 operation identity。
- 前一次 TTS 需被取消，但取消、clipboard restore 或 selection capture 不得污染下一次 trigger。
- Selection capture 失敗或為空時，才 fallback 至當下 clipboard。
- Popup active 時既有 clipboard-only suppression policy 必須另外驗證，不能與一般桌面 selection-first 情境混淆。

成功標準：

- 連續選取三段不同文字並觸發三次，依序朗讀三段最新 selection。
- 快速重觸、前一次仍在播放、clipboard restore 尚在進行等情境不會朗讀舊內容。
- Selection 為空時仍可正確 fallback 至 clipboard。

### Bug: Popup Opening Unexpectedly Speaks Clipboard

問題：

- 新增 `Ctrl+Alt+Q` 功能後，正常開啟 popup 的流程可能自動朗讀目前 clipboard。
- Popup appearance 與 speech trigger 被錯誤耦合，造成未經使用者明確要求的音訊輸出。
- 這與預期行為不同，也可能在公開場合朗讀敏感或不相關的 clipboard 內容。

需求：

- 開啟、建立、render、activate 或更新 popup 都不得自動啟動 TTS。
- 只有使用者明確觸發 `Ctrl+Alt+Q` 或按下 popup Speak button 時，才可建立 speech operation。
- 非 speech 的 `ShortcutPressInvoked`、workflow render 與 popup lifecycle 不得被誤判成 `SpeakSelectionOrClipboard`。
- Popup active 時的 clipboard-only speech policy 只適用於使用者明確觸發 speech，不代表 popup 開啟時應朗讀。
- Provider completion、workflow chaining、Back navigation、pin/unpin 與 focus event 都不得間接呼叫 speech output。

成功標準：

- 使用 `Ctrl+Alt+8`、`Ctrl+Alt+X`、follow-up 或其他 popup actions 開啟/更新 popup 時完全沒有自動朗讀。
- 只有 `Ctrl+Alt+Q` 與 Speak button 會產生 TTS operation。
- Clipboard 含文字、selection 非空或 popup 已 active 都不會改變上述規則。

### Bug: First Popup Does Not Close On Outside Click

問題：

- App 啟動後第一次出現的 popup，使用者直接點擊其他 app 或桌面時不會關閉。
- 必須先點擊 popup 一次，再點擊外部，後續 click-outside close 才正常。
- 這表示首次 popup 的 focus ownership、activation 或 FocusOut binding lifecycle 不完整。

需求：

- 第一次建立 popup 時，就必須完成 click-outside detection 的註冊與初始 focus/activation 狀態設定。
- 使用者不需要先點擊 popup；popup 顯示後直接點擊外部即可關閉。
- 點擊 popup 內的文字、按鈕、scrollbar、follow-up input 或 extension menu 不得誤關閉。
- Pinned popup 維持不因外部點擊關閉。
- 修正不得依賴 global mouse event bus；OS/Tk focus behavior 應封裝在 UI seam，close 仍透過 typed command。
- 必須處理初次 `deiconify`、topmost、focus 尚未建立以及 FocusOut 早於 view registration 等事件順序。

成功標準：

- 每次冷啟動後的第一個 popup，直接點擊桌面或其他 app 都會關閉。
- 第二次及後續 popup 行為與第一次一致。
- Popup 內部互動與 pinned 狀態不受影響。
- Unit/sim 覆蓋首次 focus lifecycle，並以真實 Windows manual smoke test 驗證。

### Popup Markdown Rendering

目標：Popup 直接呈現適合閱讀的格式，不讓使用者看到 Markdown source symbols。

需求：

- Heading、unordered/ordered list、bold、italic 與一般段落必須直接渲染。
- 使用者不應看到作為格式語法的 `#`、`-`、`*`、`**` 等符號。
- 可使用有限且一致的文字顏色協助區分 heading、重點、補充與 error，但 accessibility 與對比優先於裝飾。
- Markdown parser 與 rendering model 應位於可測的 presentation boundary；不可由 UI 以零散 regex 猜測格式。
- Copy、Paste、Archive 與 provider result 必須保留乾淨、語意正確的文字，不得被 UI style metadata 污染。
- Unsupported Markdown 必須有安全 plain-text fallback，不得造成內容消失或 popup crash。

成功標準：

- Bold、italic、heading 與 list 在 popup 中可直接辨識且沒有 Markdown 噪音。
- 長內容仍可正常 selection、copy、scroll 與 speech preprocessing。
- 同一份 parsed presentation model 可用 unit test 驗證，不依賴真實 Tk mainloop。

### Global Output Structure Prompt

產品原則：每次 LLM 輸出的核心區塊最多四個，避免使用者為理解輸出而承擔額外認知負荷。

需求：

- 在集中式 global system prompt 加入「核心內容最多四個區塊」規範，所有 action 預設繼承。
- 區塊應依使用者任務與資訊重要性組織；不得為湊格式建立低資訊量 heading。
- 每個區塊內仍需保持精簡，避免用大量 nested bullets 將複雜度藏在四個 heading 之下。
- Action-specific prompt 可要求少於四個區塊；除非產品明確允許，不得要求超過四個核心區塊。
- Output profile 與 result validation 應能偵測明顯超出區塊限制的結果，至少提供 diagnostics，不可只依賴模型自律。

成功標準：

- English Companion、shorten、follow-up 與後續 actions 的輸出都遵循最多四個核心區塊。
- 不出現重複總結、低資訊 heading 或以巢狀清單規避限制的內容。
- Global prompt 原則只有一個 ownership，避免散落在每個 action 重複維護。

### Popup Size And Reading Comfort

目標：優先處理 popup 的尺寸、留白、字級與內容密度，讓視窗舒服、清楚且能快速掃讀。

需求：

- 重新評估 popup default logical width/height、minimum size、line length、content padding、字級與行距。
- 尺寸策略必須同時符合 Windows High DPI / Display Scaling backlog，不可只針對目前螢幕寫死 pixel 值。
- 主要文字區應取得足夠空間；header、metadata、status 與 actions 不得過度壓縮內容。
- 長內容使用 scrolling，短內容避免留下不必要的大面積空白。
- 尺寸與 typography 應以實際閱讀測試調整，並建立 100% 至 200% scaling 的 manual verification matrix。

成功標準：

- 常見短、中、長輸出都具有舒適行長、清楚層級與合理留白。
- 不會因內容或 scaling 造成文字裁切、按鈕不可點或視窗超出工作區。

### Progressive Disclosure For Popup Actions

目標：預設只顯示最常用的操作，額外功能在需要時才展開，避免按鈕列造成認知負荷。

主要按鈕：

- Speak / Stop。
- Copy。
- Follow-up。

需求：

- Popup 預設 action row 維持三個主要功能，常態最多不得超過四個可見 action。
- Paste、Archive 與未來額外功能收納至右側 extension menu。
- Extension control 使用清楚的右向三角形或一致的 disclosure icon，固定靠 action row 最右側，與主要按鈕群保留視覺間距。
- 點擊 extension control 後，額外 actions 以向下展開的區域或 menu 顯示；再次點擊、點擊外部或關閉 popup 時可收合。
- Workflow 有第二、第三個 step 時，Back/chain navigation 只在需要時出現，不占用首次 popup 的主要 action 配額。
- 所有 action 的 enabled、pending、success、failure 狀態仍反映真實 lifecycle；收納不能犧牲 feedback 或 accessibility。
- Extension control 必須具備 tooltip、keyboard focus、可理解的 expanded/collapsed state 與足夠 hit target。

成功標準：

- 初次 popup 只需理解 Speak、Copy、Follow-up 三個主要按鈕。
- 額外 actions 可在一次明確操作內找到，且不與主要按鈕混成同一密集區塊。
- Back 只在 workflow history 可返回時出現。
- 使用者可不依賴動畫理解 menu 是否展開，鍵盤與高 DPI 環境仍可操作。

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

## Priority 14: Windows High DPI And Display Scaling

目標：讓 ClipAI popup 在 Windows 不同 DPI、顯示縮放比例、解析度與多螢幕環境中保持可讀、完整且可操作。

目前風險：

- 固定 pixel width/height 可能在 125%、150%、175% 或 200% scaling 下變得過大或過小。
- 文字、按鈕與內容區域可能被裁切，或因控制項太小而難以點擊。
- Popup 從一個 DPI 不同的螢幕移到另一個螢幕時，尺寸與位置可能不正確。
- 只依全螢幕解析度計算，可能超出 Windows 可用工作區或被 taskbar 遮擋。

需求：

- App 啟動時宣告正確的 Windows DPI awareness，優先支援 Per-Monitor DPI Aware 行為。
- Popup sizing 必須根據目前所在螢幕的 DPI、display scaling 與可用工作區計算，不直接依賴固定 pixel layout。
- Layout 使用 logical units、內容需求與比例限制；固定值只能作為經過 DPI conversion 的設計 token。
- 定義合理的 logical minimum size，確保標題、狀態、內容與所有可用 action button 不被裁切且保持可點擊。
- 定義最大寬高與工作區 margin，避免 popup 超出可視範圍。
- 文字、icon、button hit target、padding 與 spacing 必須隨 DPI 保持一致的實際可讀性，不得只放大外框。
- 長內容應由 scrollable content area 承擔，不得無限制放大視窗或擠壓 action controls。
- Popup 定位、cursor positioning、click-outside、drag 與 pinned workflow 在多螢幕/DPI 切換後仍須正確。
- DPI calculation 與 screen geometry 必須透過可注入的 platform/display metrics port，UI 不直接散落 Windows API 判斷。

成功標準：

- Windows 100%、125%、150%、175% 與 200% scaling 下，popup 大小合理且內容可讀。
- 主要 action buttons 全部可見、可點，不因 scaling 被裁切或重疊。
- 小螢幕、大螢幕及不同 DPI 的多螢幕環境中，popup 不超出可用工作區。
- 從一個螢幕移到另一個 DPI 不同的螢幕後，新的 popup 使用正確 metrics。
- Sizing policy 可用 fake display metrics 做 unit test，真實 Windows 行為有 integration/manual matrix。

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
- Base dialog/result surface、topmost、pin/unpin 與 click-outside close。
- Hotkey dispatcher short/long press、modifier normalization 與 atomic shortcut registry。
- Immediate popup lifecycle feedback：reading、preparing、provider、rendering、success 與 failure。
- Gemini/OpenAI/Anthropic provider adapters、fake provider、timeout/readiness 與 redacted diagnostics foundation。
- Selection-first、clipboard fallback 與 typed input resolver。
- Popup output actions：copy、paste with clipboard restore、archive、speaker/stop 與 follow-up。
- Tray startup/shutdown、operation lifecycle status 與 concurrent operation identity handling。
- Centralized output profiles、result preprocessing 與 speech-text preprocessing。
- Language-aware TTS voice selection，以及 `Ctrl+Alt+Q` selection/clipboard direct speech。
- Shortcut/action separation：`ShortcutCatalog`、typed command dispatch 與 actions schema migration。
- Composable popup workflow foundation：immutable invocation、independent cancellation、late-result guard 與 successful-step history。
- `Ctrl+Alt+X` contextual shorten workflow：short/long variant、popup selection-first、same-popup chaining 與 Back navigation。
- Context action catalog：`Ctrl+Alt+1`～`Ctrl+Alt+0` 與 `Ctrl+Alt+E` 的 typed shortcut/action mapping、multimodal-compatible prompts 與 config coverage。
- Unit/architecture regression suite covering current workflow contracts。
