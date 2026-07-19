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
  providers/        # AI provider adapter
  services/         # 業務流程與 pipeline orchestration
  services/input/   # 輸入解析與輸入 session
  ui/               # 使用者介面
  support/          # logging、diagnostics 與純通用工具
config/             # 使用者設定，放在 package 外部
  prompts/          # prompt template 與可調整的語意內容
tests/              # Unit sims 與 integration tests
```

`app` 是唯一 composition root。依賴方向固定為：`app -> services/platform/providers/ui -> core`；`support` 不得知道 ClipAI 業務模型。

## Runtime 與協調契約

- 整個程式只有一個 `AppRuntime`、一個 Tk root 與一個 Tk mainloop。
- 主流程使用直接 method call；跨 thread 使用 typed command queue。
- 禁止 global Event Bus。Event Bus 不得用來指揮 action pipeline 或修改 session。
- 每個 composable popup workflow 只有一個 `WorkflowController`，由它擁有狀態、active invocation 與成功 step history。
- Provider 採同步 contract，由單一有界 `ThreadPoolExecutor` 執行；Provider 自己不得建立 thread。
- Hotkey callback 只能 enqueue command；worker 不得直接碰 Tkinter。
- 新的未 pin action 取代舊 action；取消後晚到的結果必須依 session id/revision 丟棄。
- 所有 concrete dependency 只在 `app/container.py` 建立並注入。
- 只有 composition root 可以讀取 API key environment variables；provider 只接收已解析且不可洩漏的 credential。
- 所有 LLM/TTS operation 狀態由單一 `OperationLifecycleCoordinator` 管理；tray 不擁有 success/error timer。
- Tray menu 只能 enqueue typed command，不得直接匯出檔案、讀 config 或執行 diagnostics。
- Provider/model 選擇、設定驗證、reload 與 model catalog refresh 由單一 `ProviderConfigurationCoordinator` 擁有狀態與 operation identity；`AppRuntime` 只 dispatch、supervise worker 與投影狀態。
- 所有 provider configuration mutation 共用一個 operation gate。設定儲存或 catalog refresh 進行中，不得由 tray 或其他入口同時寫入 provider 設定。
- Provider environment mapping、credential resolution、concrete provider 建構與 `.env` persistence 屬於 app composition adapter；services 只依賴 typed backend contract。

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

## Support

`support/` 提供不屬於任何業務的通用能力。

應放入：

- logging setup。
- diagnostics flag。
- 安全診斷資料的 redaction 與 incident reference；不得知道 clipboard、prompt 或 provider payload。
- template helper。
- 純文字處理。
- 無副作用或低副作用的通用工具。

不得放入：

- Action pipeline。
- AI provider 呼叫。
- UI 呈現。
- Clipboard、keyboard、notification。
- 會改變產品流程的設定解析。

判斷方式：如果一個 helper 需要知道 ClipAI 的 action、provider、UI 或 runtime 狀態，它就不應放在 `support/`。

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

## Providers

`providers/` 負責與外部 AI 溝通。

應放入：

- OpenAI adapter。
- Gemini adapter。
- Azure OpenAI adapter。
- Ollama adapter。
- Gemini、OpenAI、Anthropic 與 fake adapter。
- 可注入的同步 HTTP transport。

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

- `providers` 可依賴 `core` 的 `LLMProvider` contract。
- `providers` 不得依賴 `ui`, `platform`, `services`, `app`。
- Provider 選擇與實例建立屬於 `app/container.py`。

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

- `services` 只能依賴 `core` 的 models 與 ports；外部能力由 `app` 注入。
- `services` 不得 import `ui`。
- 需要通知 UI 時，呼叫注入的 `ResultPresenter.render(SessionSnapshot)`。

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

- `ui` 可依賴 `core` commands、ports 與 session snapshot。
- `ui` 不得 import concrete `provider`。
- UI 操作只能送出 typed command，不得直接呼叫 service 或 concrete adapter。
- Tray 是由 `app` 注入的 `StatusIndicator` UI adapter；session status 只能透過明確 snapshot projection 更新，禁止使用 global Event Bus 或由 provider 更新 tray。

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

### Prompts

`config/prompts/` 是 prompt template 與可調整語意內容的外部化位置。

應放入：

- Action 使用的 system prompt 或 user prompt template。
- 可由使用者或產品設計調整的輸出格式、語氣、段落結構。
- 例如 summary、meaning、context、example、synonyms 這類內容組織方式。

不得放入：

- Provider API 參數或 HTTP 細節。
- UI widget layout 或 popup lifecycle。
- Clipboard、hotkey、keyboard、notification 等 platform 行為。
- Action pipeline 的控制流程。
- 需要 Python 程式才能執行的業務邏輯。

依賴與讀取規則：

- `app/config.py` 或 action config loader 可負責載入 prompt template。
- `services` 可根據 action definition 選擇並 render prompt。
- `provider` 只能接收已組好的 request，不得自行讀取 `config/prompts/`。
- `platform` 與 `ui` 不得根據 prompt template 改變自己的行為。
- prompt template 可以承載產品語意，但不應成為隱性的流程控制語言。

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

## Action feedback ownership

- Every Action referenced by a `start_action` Shortcut declares a typed, user-visible feedback contract describing the transformation, human space, verification question, and Recipe-specific reasons. Shortcut loading rejects incomplete coverage.
- Feedback semantics belong to the resolved Action, not the Shortcut. A press variant may override the base feedback contract when short and long press perform meaningfully different tasks; otherwise it inherits the base contract.
- Non-Action commands such as `speak_selection_or_clipboard` are explicitly outside this feedback lifecycle because they do not create an AI result step or Popup result.
- `WorkflowController` owns the feedback projection for the currently displayed completed step. Feedback operation identity is separate from workflow revision, provider invocation identity, and output-operation identity.
- UI emits `SubmitActionFeedback`; it never writes feedback files or mutates prompts, recipes, Action configuration, or shortcuts.
- `services` validates feedback against the immutable completed `WorkflowStep`; a platform `ActionFeedbackStore` adapter performs append-only persistence.
- Raw input and output are excluded from feedback records unless the user explicitly elects to preserve that positive or negative case.
- Feedback never changes an Action automatically. A future prompt-improvement workflow must use a separate explicit user intent, candidate version, and regression check.

## First-use guidance ownership

- `GuidancePreferencesCoordinator` is the single owner of the enabled flag, seen Action ids, and preference-operation identity.
- Tray emits typed preference intents and projects authoritative preferences; it never reads or writes JSON and never changes the checked state before persistence succeeds.
- A platform `GuidancePreferencesStore` adapter owns `data/user_preferences.json` and writes it atomically. `.env` is not a user-interaction preference store.
- A successful feedback-enabled Recipe may consume its first-use hint once per Action and press type. The Popup projects that decision as a temporary coachmark beside the existing `ⓘ`; it does not add a persistent layout row.
- Reset clears only seen Action ids. It does not enable first-use hints or change any Recipe.
