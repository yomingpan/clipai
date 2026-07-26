# Clipboard TTS Hotkey 需求規格

## 1. 產品目標

使用者在任何桌面情境下，只要按下 `Ctrl+Alt+Q`，就能立即朗讀目前想聽的文字，不必開啟 ClipAI popup，也不必經過 LLM。

系統應優先理解使用者在外部應用程式中選取的文字；若沒有選取內容，則朗讀 clipboard。當 ClipAI popup 已存在時，為避免誤讀 popup 內的 selection，改為只朗讀 clipboard。

## 2. 成功標準

此功能完成時，必須達成以下結果：

- `Ctrl+Alt+Q` 能從任何應用程式觸發 TTS。
- 一般桌面情境採用「selection 優先、clipboard fallback」。
- ClipAI 有 active session 時只讀 clipboard。
- 英文文字使用英文 voice；日文文字使用日文 voice；中文文字沿用預設 voice。
- 重複觸發會停止前一次朗讀並開始新工作。
- 整個流程不開啟新 popup、不呼叫 LLM，也不阻塞 UI thread。
- 成功或失敗狀態必須反映真實 TTS 生命週期。

## 3. 範圍

### 3.1 本次包含

- 新增 `speak_selection_or_clipboard` shortcut command 與 `Ctrl+Alt+Q` hotkey。
- 讀取目前 selection 或 clipboard。
- 依 active session 狀態決定文字來源。
- 清理適合朗讀的文字。
- 依文字內容選擇英文或預設 voice。
- 停止既有朗讀、啟動 supervised TTS worker，並追蹤執行結果。

### 3.2 本次不包含

- 自動語言偵測套件或完整語系分類。
- 讓使用者在 UI 設定每個語言的 voice。
- mixed-language 內容依段落切換 voice。
- speech queue、暫停、恢復或播放進度。
- 改變既有 popup Speak button 的行為。

## 4. 使用者體驗

### 4.1 一般桌面情境

使用者在其他應用程式選取文字後按下 `Ctrl+Alt+Q`，ClipAI 直接朗讀選取文字。

如果使用者沒有選取文字，ClipAI 改為朗讀 clipboard 文字。

### 4.2 ClipAI session 已存在

當 ClipAI 有任何 active session 時，使用者按下 `Ctrl+Alt+Q`，ClipAI 只朗讀 clipboard，不嘗試讀取 selection，以避免將 popup 內的選取內容誤認為外部應用程式 selection。

### 4.3 朗讀進行中再次觸發

系統立即要求停止目前朗讀，然後建立新的朗讀工作。連續操作不得因工作識別碼重複而遺失。

### 4.4 無可朗讀內容

selection 與 clipboard 都沒有有效文字時，系統不播放語音，也不將空內容視為錯誤。

## 5. 系統行為規則

### 5.1 觸發規則

- Shortcut ID 為 `speak_selection_or_clipboard`。
- 預設快捷鍵為 `Ctrl+Alt+Q`。
- Hotkey listener 只回報 shortcut ID 與 press type；`ShortcutCatalog` 將其解析為 typed `SpeakSelectionOrClipboard` command。
- Runtime 收到此 command 後交給 `SpeechCoordinator`，不進入一般 prompt/provider pipeline。
- Speech output 未設定時，不啟動朗讀工作。

### 5.2 文字來源規則

系統依下列順序決定來源：

1. 檢查 runtime 是否存在 active session。
2. 若存在，直接讀取 clipboard。
3. 若不存在，嘗試讀取並 trim selection。
4. Selection 非空時使用 selection。
5. Selection 為空時 fallback 至 clipboard。

### 5.3 文字處理規則

- 朗讀前套用既有 `SpeechTextPreprocessor`。
- 處理後為空字串時，不呼叫 speech adapter。
- Preprocessing 只影響送往 TTS 的文字，不修改 selection 或 clipboard 原文。

### 5.4 Voice 選擇規則

- 文字包含平假名、片假名、片假名語音擴充或半形片假名時，使用 `tts.japanese_voice`，預設為 `ja-JP-NanamiNeural`。
- 非日文文字若包含 `U+4E00` 至 `U+9FFF` 任一字元，不指定 voice override，交由 adapter 使用設定中的預設 voice。
- 其餘文字使用 `tts.english_voice`，預設為 `en-US-AndrewNeural`。
- Speech port 接受 immutable `SpeechRequest(text, voice_override, cancellation)`。

### 5.5 工作生命週期規則

- 每次觸發前先要求停止目前朗讀。
- 每次觸發建立唯一 operation ID：`tts:clipboard:<unique-value>`。
- TTS 必須由 `TaskSupervisor` 在 worker thread 執行。
- 有 operation tracker 時，工作開始、成功、失敗都必須對應真實執行狀態。
- Speech adapter 發生例外時，operation 標記失敗，並交由既有 speech error handler 處理。
- 不得在 TTS 真正完成前標記成功。
- 新工作以獨立 cancellation token 取代舊工作；舊工作晚完成不得覆蓋新工作狀態。

## 6. 系統責任分層

### 6.1 Core contract

- `SpeechOutput` 定義 `speak(SpeechRequest)` 與 `stop()`。
- Contract 保持 toolkit 與 provider 無關。

### 6.2 Platform adapters

- Selection adapter 負責從作業系統取得目前選取文字。
- Clipboard adapter 負責讀取 clipboard。
- Speech adapter 負責套用 voice override、產生及播放音訊。
- Platform 不決定 selection-first、session suppression 或語言政策。

### 6.3 Services

- `ShortcutCatalog` 負責將 shortcut trigger 解析為 typed command。
- `SpeechCoordinator` 負責 selection-first、clipboard fallback、preprocessing、取消與 operation lifecycle。
- `SpeechVoiceSelector` 負責 CJK 判斷與 voice override 政策。
- `OutputActions` 僅保留 popup output actions，不承擔全域 hotkey speech policy。

### 6.4 App runtime

- Dispatch `SpeakSelectionOrClipboard` command。
- 依 active session 狀態選擇 clipboard-only 或 selection-first 流程。
- 將明確的 `clipboard_only` context 傳給 coordinator。
- 提交 coordinator 建立的唯一 speech job 並處理未捕捉錯誤。

### 6.5 Composition root

- `app.container` 建立並注入 concrete `SelectionReader`。
- UI 與 service 不得自行建立 platform adapter。
- UI 不得直接讀 clipboard、selection 或呼叫 TTS。

## 7. 驗收條件

### AC-1：選取文字優先

Given 沒有 active session，selection 為 `selected text`，clipboard 為 `clipboard text`
When 使用者按下 `Ctrl+Alt+Q`
Then 系統朗讀 `selected text`，並使用 `en-US-AndrewNeural`。

### AC-2：clipboard fallback

Given 沒有 active session，selection 為空，clipboard 為 `clipboard text`
When 使用者按下 `Ctrl+Alt+Q`
Then 系統朗讀 `clipboard text`。

### AC-3：active session 抑制 selection

Given 至少有一個 active session，且 selection 非空
When 使用者按下 `Ctrl+Alt+Q`
Then 系統不得讀取 selection，只朗讀 clipboard。

### AC-4：中文沿用預設 voice

Given 要朗讀的文字為 `你好，世界`
When TTS 執行
Then speech adapter 收到的 voice override 為 `None`。

### AC-5：非 CJK 使用英文 voice

Given 要朗讀的文字為 `Hello world`
When TTS 執行
Then speech adapter 收到 `en-US-AndrewNeural`。

### AC-6：日文使用日文 voice

Given 要朗讀的文字為 `これは日本語です。`
When TTS 執行
Then speech adapter 收到 `ja-JP-NanamiNeural`。

### AC-7：重複觸發

Given 使用者連續觸發兩次快捷鍵
When runtime 建立兩次 TTS 工作
Then 兩個 supervisor work key 必須不同，且每次皆先要求停止既有朗讀。

### AC-8：空內容

Given 最終文字經 preprocessing 後為空
When TTS 工作執行
Then speech adapter 不得被呼叫。

### AC-9：失敗狀態

Given speech adapter 執行失敗
When worker 回報例外
Then operation 標記 failed，且不得提前顯示 success。

## 8. 測試策略

### 8.1 Unit / sims

- 英文 clipboard 使用英文 voice。
- CJK clipboard 沿用預設 voice。
- Selection-first 與 clipboard fallback。
- Active session 時只使用 clipboard。
- Preprocessing 後空內容不呼叫 speech。
- 每次觸發產生不同 operation / supervisor key。
- Speech unavailable、speech exception 與 stop-before-restart。

### 8.2 Integration / manual smoke

- 在一般 Windows 應用程式選取文字後按 `Ctrl+Alt+Q`。
- 未選取文字時朗讀 clipboard。
- ClipAI popup 開啟且內文有 selection 時，仍只朗讀 clipboard。
- 朗讀途中再次觸發，前一次停止且新內容開始朗讀。
- 中英文內容使用預期 voice。
- 確認流程不開啟新 popup，也不呼叫 LLM provider。

## 9. 已知限制

- 日文判斷依賴平假名或片假名；只有漢字的短字串無法與中文可靠區分，仍沿用預設 voice。
- 所有未命中日文或 CJK 規則的文字都使用英文 voice，包括其他非英文語言。
- Active session 的判斷是 runtime session collection 非空，不限於目前可見的 popup。
