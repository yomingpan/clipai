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
  services/         # 業務流程、輸入解析與 pipeline orchestration
  ui/               # 使用者介面
  support/          # logging、diagnostics 與純通用工具
config/             # 使用者設定，放在 package 外部
tests/              # Unit sims 與 integration tests
```

`app` 是唯一 composition layer。`app/container.py` 是組裝入口；focused app composition adapters 可以在 typed service contract 背後建立或重建 concrete dependency。依賴方向固定為：`app -> services/platform/providers/ui -> core`；`support` 不得知道 ClipAI 業務模型。

## Runtime 與協調契約

- 整個程式只有一個 `AppRuntime`、一個 Tk root 與一個 Tk mainloop。
- 主流程使用直接 method call；跨 thread 使用 typed command queue。
- 禁止 global Event Bus。Event Bus 不得用來指揮 action pipeline 或修改 Workflow。
- 每個 Workflow 只有一個 `WorkflowController`，由它擁有 snapshot、active invocation、cancellation、成功 step history 與 feedback projection。
- `WorkflowRuntimeModule` 是 Workflow membership、semantic Foreground Workflow、visible/headless lifetime 與 captured provider binding 的唯一 owner。Window focus 只能提出 activation candidate，不得自行決定 Foreground Workflow。
- `ProviderExecutionModule` 是 provider async HTTP task、transport cancellation、settlement、shared connection pool 與 transport shutdown 的唯一 owner。Provider networking 不得占用 `TaskSupervisor`；`TaskSupervisor` 只執行非 provider 的 blocking work。
- Hotkey callback 只能 enqueue command；worker 不得直接碰 Tkinter。
- 同一時間最多一個 visible Workflow 擁有主要 Popup surface。PIN 會保留並占用該 surface；新的 visible Action 必須重用既有 pinned Workflow 與同一個 Popup，不得建立第二個 surface，也不得要求使用者先取消 PIN。未 pin Workflow 才可被非 contextual Action 取代；被取代或取消的 invocation 晚到時，必須依 Workflow ID、active invocation ID 與 cancellation token 丟棄。Workflow snapshot revision 只用於拒絕過時的 UI projection，不得代替 operation identity。
- `app/container.py` 負責 assembly；需要在 runtime reload 或設定變更後重建的 concrete dependency，可由 focused app composition adapter 建立並透過 typed backend contract 注入 services。
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
- 抽象介面，例如 `LLMProvider`, `ApplicationView`, `ResultPresenter`, `ArchiveStore`。
- Typed command 與跨層 payload contract。
- 取消機制與跨層共用 contract。

不得放入：

- OpenAI、Gemini、Ollama 等具體 provider。
- Tkinter、tray、WebView、notification。
- Clipboard、keyboard、microphone、filesystem 等 OS 細節。
- 任何讀取 `config/` 或環境變數後改變產品行為的邏輯。

依賴規則：

- `core` 不得 import `app`, `services`, `ui`, `platform`, `providers`。
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
- 受控 Edge WebView2 Browser Speech host 與 engine adapter。
- File system output。

不得放入：

- Prompt 決策。
- Action 選擇。
- AI provider 呼叫。
- Popup layout 或 button 行為。
- 使用者是否應該看到某個結果的決策。

依賴規則：

- `platform` 可依賴 `core` 的 contract 或常數。
- `platform` 不得依賴 `ui` 或 `providers`。
- `platform` 不應主動驅動業務流程，只提供可替換的外部能力。

## Providers

`providers/` 負責與外部 AI 溝通。

應放入：

- OpenAI adapter。
- Gemini adapter。
- Azure OpenAI adapter。
- Ollama adapter。
- Gemini、OpenAI、Anthropic 與 fake adapter。
- 共用 async HTTP transport 上的 provider adapter。

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
- Provider 選擇狀態屬於 `ProviderConfigurationCoordinator`；concrete provider 建構屬於 `app` composition adapter，`app/container.py` 負責初始組裝。

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
- Voice capture policy 與可測的 Voice Draft transition。

輸入相關 service 目前直接放在 `services/`，包括：

- Input resolver。
- Input target resolver。
- Clipboard transaction coordinator。

Services 負責把能力串起來，例如：

```text
hotkey -> input -> safety/config -> prompt -> provider -> postprocess -> output
```

`WorkflowController` 仍是 Workflow snapshot、history、render 與 lock scope 的唯一 owner。`services/voice_draft.py` 只封裝無狀態、無副作用的 Voice Draft transition：它不得儲存 snapshot、持有 lock、呼叫 presenter，或形成第二套 Workflow state owner。

不得放入：

- Tkinter widget 或 popup layout。
- Provider HTTP API 細節。
- OS-specific clipboard implementation。
- 直接 `dialog.show()`。

依賴規則：

- `services` 只能依賴 `core` 的 models 與 ports；外部能力由 `app` 注入。
- `services` 不得 import `ui`。
- 需要通知 UI 時，呼叫注入的 `ResultPresenter.render(...)`。目前 projection type 名為 `SessionSnapshot`，它是 Workflow projection 的相容名稱，不代表另一個 Session identity。

## UI

`ui/` 是使用者看得到與操作得到的部分。

應放入：

- Tray。
- Dialog。
- Floating popup。
- Settings UI。
- Voice setup 與 Voice Draft presentation。
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

- `ui` 可依賴 `core` commands、ports 與 Workflow snapshot projection。
- `ui` 不得 import concrete `providers`。
- UI 操作只能送出 typed command，不得直接呼叫 service 或 concrete adapter。
- Tray 是由 `app` 注入的 `StatusIndicator` UI adapter；Workflow 與 operation status 只能透過明確 projection 更新，禁止使用 global Event Bus 或由 provider 更新 tray。

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
- `config/shortcuts.yaml`
- `config/output_profiles.yaml`

目標是避免把產品行為硬寫進程式。程式可以定義 schema、預設值、validation，但可調整內容應盡量外部化。

### Prompts

Prompt template 與可調整語意內容目前放在 `config/actions.yaml` 的 Action definition。未來若引入 `config/prompts/`，必須由同一個 config-loader boundary 載入，不得形成第二套 prompt ownership。

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

- `app/config_loader.py` 負責載入 Action 與 prompt template。
- `services` 可根據 action definition 選擇並 render prompt。
- `providers` 只能接收已組好的 request，不得自行讀取 Action config 或 prompt template。
- `platform` 與 `ui` 不得根據 prompt template 改變自己的行為。
- prompt template 可以承載產品語意，但不應成為隱性的流程控制語言。

## 常見判斷範例

- 新增 Gemini 串接：放 `providers/`。
- 新增 popup button：放 `ui/`。
- 新增 action pipeline step：放 `services/`。
- 新增 LLM 抽象 method：放 `core/`。
- 新增 hotkey 行為：放 `platform/`。
- 新增 logging context helper：放 `support/`，前提是它不知道 ClipAI 業務模型。
- 新增 prompt template：放 `config/actions.yaml`；若引入獨立檔案，仍由 `app/config_loader.py` 載入。
- 新增 config 欄位解析：放 `app/config_loader.py`；可測的 Action policy 放 `services/action_catalog.py`。

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

- Every Action referenced by a `start_action` Shortcut declares a typed, user-visible feedback contract describing what AI helps with, what AI does not decide, and Recipe-specific feedback reasons. Shortcut loading rejects incomplete coverage.
- Feedback semantics belong to the resolved Action, not the Shortcut. A press variant may override the base feedback contract when short and long press perform meaningfully different tasks; otherwise it inherits the base contract.
- Non-Action commands such as `speak_selection_or_clipboard` are explicitly outside this feedback lifecycle because they do not create an AI result step or visible Workflow result.
- `WorkflowController` owns the feedback projection for the currently displayed completed step. Feedback operation identity is separate from workflow revision, provider invocation identity, and output-operation identity.
- UI emits `SubmitActionFeedback`; it never writes feedback files or mutates prompts, recipes, Action configuration, or shortcuts.
- `services` validates feedback against the immutable completed `WorkflowStep`; a platform `ActionFeedbackStore` adapter performs append-only persistence.
- Raw input and output are excluded from feedback records unless the user explicitly elects to preserve that positive or negative case.
- Feedback never changes an Action automatically. A future prompt-improvement workflow must use a separate explicit user intent, candidate version, and regression check.

## User preferences ownership

- `UserPreferencesCoordinator` is the single owner of first-use guidance, Speech Speed, and preference-operation identity. Explicit preference writes share one operation gate because they update the same persisted aggregate.
- Tray emits typed preference intents and projects authoritative preferences; it never reads or writes JSON and never changes the checked state before persistence succeeds.
- A platform `UserPreferencesStore` adapter owns `data/user_preferences.json` and writes it atomically. `.env` remains independently owned provider configuration and does not share this gate.
- First-use hints are disabled by default and the tray toggle is initially unchecked. When explicitly enabled, a successful feedback-enabled Recipe may consume its first-use hint once per Action and press type. The visible Workflow surface projects that decision as a temporary coachmark beside the existing `ⓘ`; it does not add a persistent layout row.
- Legacy preference schema v1 migrates to disabled while preserving seen Action ids, and schema v2 loads without a Speech Speed override. Schema v3 persists subsequent explicit choices.
- Reset clears only seen Action ids. It does not enable first-use hints or change any Recipe.
- Missing Speech Speed preserves `config.yaml`'s `tts.rate`; the four known rates project as presets and any other legacy rate projects as Custom until the user explicitly selects a preset.
- A speech request captures the current persisted speed when its worker starts. Later preference changes affect only subsequent speech and never mutate, stop, or restart active playback.

## Runtime ownership additions (ADR-0002 / ADR-0003)

- `ProviderExecutionModule` exclusively owns async provider HTTP tasks, transport cancellation, connection pooling, and transport shutdown.
- `TaskSupervisor` owns only non-provider blocking work and isolates interactive, media, and maintenance capacity.
- One container-scoped `ClipboardTransactionCoordinator` owns selection and paste clipboard transactions.
- Workflow snapshots enter the UI through a per-Workflow latest-revision mailbox. Ordered output-operation acknowledgements remain separate and are never coalesced.
- `PopupExternalOutputTransitions` is the single UI-internal owner of Popup
  output-operation identity, stale acknowledgement rejection, Paste visibility,
  captured pin policy, and toolkit focus generations. It returns explicit UI
  actions; widgets and presenters only execute those actions.

## Paste Operation ownership (ADR-0004)

- `PasteOperationCoordinator` is the single owner of Paste Operation identity,
  global active membership, at-most-once execution, cooperative cancellation,
  Paste Dispatch truth, and the combined delivery/clipboard-cleanup outcome.
- `ClipboardTransactionCoordinator` remains the only owner of temporary
  clipboard mutation. Paste orchestration uses that owner; it does not create a
  second lock, snapshot, sequence, or restore path.
- Runtime schedules a Paste Operation and projects its typed outcome. Runtime
  and UI must not infer target consumption from task completion, a fixed delay,
  focus, visibility, or clipboard sequence changes.
- Runtime carries Paste operation identities only. It must not retain a concrete
  Paste operation handle or a parallel registry. `TaskSupervisor` owns worker
  scheduling, not Paste membership or settlement.
- The container admits one Paste Operation at a time. Overlap is rejected with
  an identified failure; it is never queued and never replaces active work.
- Cancellation is an intent. A running Paste Operation remains active until the
  coordinator knows dispatch and cleanup truth. Exactly one typed
  `PasteOperationCompleted` command carries that truth back through the ordered
  application command queue.
- `AppRuntime` routes that completion to output settlement and to
  `WorkflowRuntimeModule`. Only the Workflow runtime may release semantic
  Foreground Workflow, and only for the current visible, unpinned Workflow after
  `dispatched_unconfirmed`.
- Paste acknowledgement has no `succeeded` state. Legal terminal states are
  `failed`, `cancelled`, `dispatched_unconfirmed`, and `cleanup_failed`.
- Platform paste adapters own modifier state, target validation, activation,
  final foreground validation, and input injection. Returning from input
  injection proves dispatch only, not target consumption.
- Clipboard Preservation is fail-closed. Unsupported non-redundant native
  formats stop the Paste Operation before clipboard mutation and dispatch.

## Canonical content, presentation, and selection ownership

- Canonical result content is semantic data, independent of widget styling and
  presentation parsing. Copy, paste, archive, and speech receive canonical text
  or an explicit semantic selection; they never reconstruct content from widget
  tags, rendered spans, or Markdown appearance.
- `services` owns presentation parsing and produces a typed immutable
  `PresentationDocument`. UI adapters render that document. Unsupported syntax
  degrades to safe plain text without changing canonical content or crashing the
  surface.
- A Popup selection is resolved at the UI presentation boundary and carried in
  the typed output command. It takes precedence over the displayed step's
  canonical content. The runtime does not read a Tk widget to recover it.
- For an external text-capable Action, selection is captured at the instant of
  explicit user intent. A valid selection takes precedence; otherwise input
  falls back to the configured clipboard policy. Selection capture and Paste
  share the one container-scoped `ClipboardTransactionCoordinator`, so capture
  cannot permanently replace newer clipboard content.
- Workflow identity, output-operation identity, selection-capture identity, and
  view lifecycle remain distinct. A Workflow snapshot revision cannot stand in
  for any of those operation identities.

## Output Profile ownership

- `OutputProfileCatalog` owns reusable output-format instruction,
  presentation mode, and structural marker validation. `PromptBuilder` consumes
  the instruction and `ResultProcessor` consumes the same resolved profile.
- An Action owns task semantics and genuinely Action-specific output content. It
  references a profile ID; it must not create a second reusable presentation
  schema that drifts from the catalog.
- Configuration loading rejects unknown profile IDs. Tests must keep prompt
  injection, result processing, and Action/variant resolution on the same
  catalog entry.
- Existing Action prompts that duplicate reusable profile wording are migration
  debt, not a second accepted owner. Remove them incrementally only with prompt
  regression coverage; do not silently change prompt behavior during unrelated
  architecture or documentation work.
