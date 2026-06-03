# Repository Guidelines

## Project Structure & Module Organization
`clipai/` 放置主要應用程式碼。`app/` 負責 runtime 組裝，`services/` 放工作流程邏輯，`ui/` 放畫面呈現與互動，`providers/` 放 LLM 串接，`platform/` 放作業系統介面，`context/` 處理輸入解析，`core/` 放共用事件、取消機制與 provider contract。`tests/` 依這些區域放置對應測試。runtime 設定在 `config/config.yaml` 與 `config/actions.yaml`。本機產生的執行資料應放在 `logs/`、`output/` 與 `temp_audio/`。

未來結構重排時，依 [Architecture Boundaries](docs/ARCHITECTURE_BOUNDARIES.md) 收斂到 `core/platform/provider/services/ui/utils/app`。測試策略依 [Testing Strategy](docs/TESTING_STRATEGY.md) 執行。

## Build, Test, and Development Commands
開發前先啟用本機 virtual environment：

```powershell
& c:\Users\88698\ClipAI_v2\.venv\Scripts\Activate.ps1
```

使用 `python main.py` 在本機啟動 app。使用 `python -m pytest` 執行預設快速測試。使用 `python -m pytest -m integration` 手動執行會碰真實 OS/UI 的整合測試。需要聚焦單一檔案時，可執行 `python -m pytest tests/services/test_action_runner.py`。使用 `python -m compileall clipai` 檢查 import 與語法健康度。

## Coding Style & Naming Conventions
使用 Python 3.11 與四格縮排。維持既有架構邊界：UI 不直接 import providers，services 不 import UI，providers 不依賴 UI、event bus、clipboard 或 tray 程式碼。函式、變數與模組使用 `snake_case`；class 與 dataclass 使用 `PascalCase`。結構化狀態優先使用 typed dataclass，依賴關係優先用明確注入，避免新增全域存取。

## Testing Guidelines
測試使用 `pytest`，並放在 `tests/`。測試檔命名為 `test_*.py`，測試函式命名為 `test_*`。修改 service workflow、provider 行為、config parsing 或架構邊界時，應在相近位置新增或更新測試。預設測試不得碰真實網路、真實剪貼簿、真實鍵盤 listener 或真實 UI mainloop；這些情境應標記為 `integration` 並手動執行。

## Commit & Pull Request Guidelines
commit message 使用簡短祈使句，風格對齊既有歷史，例如 `Add WebView voice input hotkey`、`Improve TTS streaming latency` 或 `Refactor popup lifecycle`。Pull request 應描述使用者可見變更、列出已執行的主要測試、說明設定檔變更；若影響 UI、tray、語音輸入或通知行為，請附截圖或關鍵 log。

## Security & Configuration Tips
不要提交 `.env`、憑證、provider API keys、logs、產生的音訊或 archived output。可分享的預設值放在 `.env.example` 與 `config/`。新增必要設定時，請同步記錄用途與預期格式。

# ClipAI Core Philosophy

## Product Mantra
Think Clearly. Move Powerfully.

This philosophy is the source of truth for ClipAI product decisions, interface design, technical architecture, and brand communication. If a feature violates this document, it should not be implemented even if it looks impressive.

## Core Belief
The human holds the steering wheel.

AI is the power system and assistance system. ClipAI does not believe in autopilot. ClipAI believes in human-driven work with intelligent assistance:

- Humans choose direction.
- AI reduces resistance.
- Humans make judgments.
- AI amplifies judgment.

## Brand Core
Clarity + Freedom -> Decisive Action.

Clarity creates freedom. Freedom enables decisive action. ClipAI does not pursue speed for its own sake. ClipAI pursues clarity, because only people who see clearly can truly move forward.

## Driving Philosophy
ClipAI is not fundamentally about answering questions. It exists to preserve the user's decision space.

AI is responsible for reducing noise, marking ambiguity, illuminating blind spots, and helping identify uncertainty.

AI is not responsible for making decisions, providing direction, or taking over judgment.

ClipAI does not push the user. It helps the user see the road they are already choosing to walk.

## AI Behavior Principles
ClipAI responses should be brief, restrained, precise, question-first when appropriate, and spacious enough to preserve the user's thinking room.

When input contains ambiguous information, unverified assumptions, contradictions, or missing context, ClipAI should explicitly mark:

`⚠️ 模糊點`

Then it should state whether the ambiguity affects directional judgment and whether it needs confirmation. ClipAI should not fill ambiguity on behalf of the user. It should only illuminate it.

## Anxiety Handling Principles
ClipAI respects user autonomy:

- Do not block: do not restrict user operations.
- Do not judge: do not criticize user behavior.
- Do not monitor: do not analyze or monitor user emotions.
- Do not take over: do not make decisions for the user.

ClipAI is not responsible for fixing the user. It is responsible for illuminating the present moment.

## Product Positioning
ClipAI is a Thinking Accelerator.

It is a low-friction interaction layer between humans and AI. It helps users quickly invoke AI, continue thinking, organize thoughts, and advance decisions. The user always keeps control. ClipAI does not replace thinking. ClipAI returns thinking to the human.

## Long-Term Product Direction
ClipAI rejects show-off AI. Do not pursue looking impressive, manufacturing surprise, dopamine stimulation, or addictive usage.

Pursue stability, predictability, understandability, intervenability, and controllability. Users should always know what the system is doing and retain the right to intervene.

## Core Feature Directions
ClipAI has only three core capabilities:

- Instant Access: the shortest path into AI.
- Pipeline Thinking: the previous output can become the next input.
- Voice Interface: when eyes are tired, ears can take over.

## Friction Philosophy
Preserve cognitive friction because it promotes thinking, judgment, reflection, and choice.

Remove operational friction such as extra button presses, repeated operations, meaningless switching, and unnecessary waiting.

## Development Rhythm
ClipAI does not grow by stacking features. It grows through:

Add -> Use -> Validate -> Prune.

Features that do not become habits are suspicious. Features that do not create clear value should be delayed, simplified, or removed. Less is often stronger than more.

## Final Definition
ClipAI does not provide direction.

ClipAI helps you see direction clearly.

Direction is always decided by you.

AI accelerates.

Humans drive.
