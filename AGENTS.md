# Repository Guidelines

## Project Structure & Module Organization
`clipai/` 放置主要應用程式碼。`app/` 負責 runtime 組裝，`services/` 放工作流程邏輯，`ui/` 放畫面呈現與互動，`providers/` 放 LLM 串接，`platform/` 放作業系統介面，`context/` 處理輸入解析，`core/` 放共用事件、取消機制與 provider contract。`tests/` 依這些區域放置對應測試。runtime 設定在 `config/config.yaml` 與 `config/actions.yaml`。本機產生的執行資料應放在 `logs/`、`output/` 與 `temp_audio/`。

## Build, Test, and Development Commands
開發前先啟用本機 virtual environment：

```powershell
& c:\Users\88698\ClipAI_v2\.venv\Scripts\Activate.ps1
```

使用 `python main.py` 在本機啟動 app。使用 `python -m pytest` 執行完整測試。需要聚焦單一檔案時，可執行 `python -m pytest tests/services/test_action_runner.py`。使用 `python -m compileall clipai` 檢查 import 與語法健康度。

## Coding Style & Naming Conventions
使用 Python 3.11 與四格縮排。維持既有架構邊界：UI 不直接 import providers，services 不 import UI，providers 不依賴 UI、event bus、clipboard 或 tray 程式碼。函式、變數與模組使用 `snake_case`；class 與 dataclass 使用 `PascalCase`。結構化狀態優先使用 typed dataclass，依賴關係優先用明確注入，避免新增全域存取。

## Testing Guidelines
測試使用 `pytest`，並放在 `tests/`。測試檔命名為 `test_*.py`，測試函式命名為 `test_*`。修改 service workflow、provider 行為、config parsing 或架構邊界時，應在相近位置新增或更新測試。提交前執行 `python -m pytest`。

## Commit & Pull Request Guidelines
commit message 使用簡短祈使句，風格對齊既有歷史，例如 `Add WebView voice input hotkey`、`Improve TTS streaming latency` 或 `Refactor popup lifecycle`。Pull request 應描述使用者可見變更、列出已執行的主要測試、說明設定檔變更；若影響 UI、tray、語音輸入或通知行為，請附截圖或關鍵 log。

## Security & Configuration Tips
不要提交 `.env`、憑證、provider API keys、logs、產生的音訊或 archived output。可分享的預設值放在 `.env.example` 與 `config/`。新增必要設定時，請同步記錄用途與預期格式。
