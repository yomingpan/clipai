# ClipAI 模組邊界規範

本文件定義 ClipAI 的架構邊界。未來新增功能、重構、測試設計，都應先對照這份文件。

ClipAI 採用 Clean Architecture / Onion Architecture。核心原則是：

> 越靠近中心的東西越穩定。越靠近外圍的東西越容易被替換。

依賴方向只能由外往內。核心邏輯不應知道外部世界長什麼樣子。

## 目標結構

```text
clipai/
  app/              # 組裝層與 runtime 啟動
  core/             # 核心抽象、事件、domain contract
  platform/         # 作業系統與裝置接縫
  provider/         # AI provider adapter
  services/         # 業務流程與 pipeline orchestration
  services/input/   # 輸入解析與輸入 session
  ui/               # 使用者介面
  utils/            # 通用工具
config/             # 使用者設定，放在 package 外部
tests/              # Unit sims 與 integration tests
```

目前 repo 仍可能存在過渡中的舊路徑，例如 `providers/` 或 `context/`。重構時應朝上方結構收斂，不新增新的長期依賴到舊路徑。

## Core

`core/` 是最穩定的中心層。

應放入：

- 產品規則與領域模型。
- 抽象介面，例如 `LLMProvider`, `UIGateway`, `MemoryStore`。
- 事件名稱、事件 payload contract。
- 取消機制與跨層共用 contract。

不得放入：

- OpenAI、Gemini、Ollama 等具體 provider。
- Tkinter、tray、WebView、notification。
- Clipboard、keyboard、microphone、filesystem 等 OS 細節。
- 任何讀取 `config/` 或環境變數後改變產品行為的邏輯。

依賴規則：

- `core` 不得 import `app`, `services`, `ui`, `platform`, `provider`。
- `core` 可以被所有其他層依賴。

## Utils

`utils/` 提供不屬於任何業務的通用能力。

應放入：

- logging setup。
- diagnostics flag。
- template helper。
- 純文字處理。
- 無副作用或低副作用的通用工具。

不得放入：

- Action pipeline。
- AI provider 呼叫。
- UI 呈現。
- Clipboard、keyboard、notification。
- 會改變產品流程的設定解析。

判斷方式：如果一個 helper 需要知道 ClipAI 的 action、provider、UI 或 runtime 狀態，它就不應放在 `utils/`。

## Platform

`platform/` 是真實作業系統與裝置的接縫。

應放入：

- Clipboard read/write。
- Hotkey listener。
- Keyboard paste。
- Notification。
- TTS/STT engine。
- Microphone/audio。
- File system output。

不得放入：

- Prompt 決策。
- Action 選擇。
- AI provider 呼叫。
- Popup layout 或 button 行為。
- 使用者是否應該看到某個結果的決策。

依賴規則：

- `platform` 可依賴 `core` 的 contract 或常數。
- `platform` 不得依賴 `ui` 或 `provider`。
- `platform` 不應主動驅動業務流程，只提供可替換的外部能力。

## Provider

`provider/` 負責與外部 AI 溝通。

應放入：

- OpenAI adapter。
- Gemini adapter。
- Azure OpenAI adapter。
- Ollama adapter。
- Provider factory。

責任只有兩個：

- 把 ClipAI 的統一 request 轉成各家 API 格式。
- 把各家 API result 轉回 ClipAI 的統一 result。

不得放入：

- UI 狀態。
- Tray notification。
- Clipboard 或 keyboard 操作。
- Action pipeline 決策。
- Memory 或 archive 寫入。

依賴規則：

- `provider` 可依賴 `core` 的 `LLMProvider` contract。
- `provider` 不得依賴 `ui`, `platform`, `services`。
- `provider` 不得直接使用 event bus singleton。

## Services

`services/` 是業務流程的大腦。

應放入：

- Action runner。
- Action service。
- Pipeline coordinator。
- Hedged request。
- Output orchestration。
- Memory。
- Archive。
- Model manager。
- Voice transcription workflow。

`services/input/` 應放入：

- Input resolver。
- Clipboard session。
- Runtime input context。

Services 負責把能力串起來，例如：

```text
hotkey -> input -> safety/config -> prompt -> provider -> postprocess -> output
```

不得放入：

- Tkinter widget 或 popup layout。
- Provider HTTP API 細節。
- OS-specific clipboard implementation。
- 直接 `dialog.show()`。

依賴規則：

- `services` 可依賴 `core`, `platform`, `provider` contract 或由 `app` 注入的具體能力。
- `services` 不得 import `ui`。
- 需要通知 UI 時，使用 `UIGateway`、callback 或 event。

## UI

`ui/` 是使用者看得到與操作得到的部分。

應放入：

- Tray。
- Dialog。
- Floating popup。
- Settings UI。
- WebView voice input。
- Popup button handler。

UI 只負責：

- 顯示狀態。
- 接收操作。
- 把操作轉成 callback/event。

不得放入：

- AI provider 呼叫。
- Prompt 決策。
- Action pipeline。
- Memory persistence policy。
- Provider fallback 或 hedged request 決策。

依賴規則：

- `ui` 可依賴 `core` event contract 與 service session model。
- `ui` 不得 import concrete `provider`。
- UI 需要服務時，應透過 callback、gateway 或 `app` 注入。

## App

`app/` 是 Composition Root。

應放入：

- Runtime startup。
- Config loading。
- Dependency wiring。
- Provider、platform、service、UI 的實例建立與接線。

只有 `app/` 可以知道「誰依賴誰」。

不得放入：

- Provider HTTP 細節。
- Popup widget 細節。
- 可獨立測試的 action pipeline 邏輯。

## Config

`config/` 是使用者設定資料夾，永遠放在 package 外部。

應放入：

- `config/config.yaml`
- `config/actions.yaml`
- `config/prompts/`

目標是避免把產品行為硬寫進程式。程式可以定義 schema、預設值、validation，但可調整內容應盡量外部化。

## 常見判斷範例

- 新增 Gemini 串接：放 `provider/`。
- 新增 popup button：放 `ui/`。
- 新增 action pipeline step：放 `services/`。
- 新增 LLM 抽象 method：放 `core/`。
- 新增 hotkey 行為：放 `platform/`。
- 新增 logging context helper：放 `utils/`。
- 新增 prompt template file：放 `config/prompts/`。
- 新增 config 欄位解析：放 `app/config.py` 或 `services/actions.py`。

## 禁止案例

- UI 直接呼叫 OpenAI provider。
- Provider 發 tray notification。
- Core 讀 clipboard。
- Service 直接 `dialog.show()`。
- Platform 決定 action prompt。
- Utility 讀 app config 並改變產品行為。

## 最終原則

架構的目的不是把資料夾切漂亮。

架構的目的，是讓每個真實世界接觸點都能被拔掉，換成假的測試接縫，讓核心邏輯可以快速、穩定、可預測地被驗證。
