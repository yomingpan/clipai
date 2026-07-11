# ClipAI 測試架構策略

本文件定義 ClipAI 的測試哲學與測試分層。

核心思想：

> 可測試性就是架構預留的插頭。

ClipAI 一開始就要把系統切成幾個好替換的接縫。像家電插頭一樣，要測試時能把真實世界那些麻煩的東西先拔掉，換成假的來跑。這樣核心邏輯就能很快、很穩地驗證。

## 測試成功來自架構接縫

測試的成功來自 Clean Architecture / Onion Architecture。

業務邏輯只依賴抽象介面，例如：

- `LLMProvider`
- `UIGateway`
- typed command queue
- `SessionController`
- Clipboard/Input abstraction
- Output abstraction

測試時就能在這些接縫注入 fake 或 mock，把南側的外部世界整個換掉：

- LLM API
- 剪貼簿
- Tkinter
- WebView
- 鍵盤
- 通知
- TTS/STT

因此，架構的結構本身就是可驗證性的基礎。

## 雙層測試模型

ClipAI 測試分成兩層。

### Unit / Sims Tests

這是預設測試層。

特性：

- 快。
- 穩。
- 不碰網路。
- 不開真實 UI。
- 不碰真實剪貼簿。
- 不送真實鍵盤事件。
- 使用 fake provider、fake presenter、fake clipboard、in-memory command queue。

目的：

- 快速驗證核心流程。
- 改完程式馬上得到回饋。
- 讓重構不害怕。

預設執行：

```powershell
python -m pytest
```

GitHub Windows CI 必須在 Python 3.10、3.11、3.12、3.13 執行 constrained clean install、compile、unit tests 與 architecture tests。排程工作另測未鎖定依賴，但不得影響正式安裝 constraints。

### Integration Tests

這是手動觸發的真實世界測試。

特性：

- 比較慢。
- 比較接近真實使用情境。
- 可以碰剪貼簿、鍵盤、畫面、通知、TTS/STT。
- 專門驗證混亂情境下是否穩定。

目的：

- 驗證 OS 與 UI 接縫。
- 驗證使用者操作弱點。
- 驗證 race condition、focus、clipboard restore、button click、streaming UI。

手動執行：

```powershell
python -m pytest -m integration
```

## Tests Folder 結構

目標結構：

```text
tests/
  conftest.py
  helpers/
    fake_provider.py
    fake_presenter.py
    fake_clipboard.py
    hotkey_driver.py
    popup_driver.py
  unit/
    core/
    services/
    platform/
    provider/
    ui/
    config/
  integration/
    platform/
    ui/
    runtime/
```

目前 repo 可以漸進搬移既有測試。新增測試時，優先放進 `unit/` 或 `integration/`；舊測試不用為了命名一次搬完。

## conftest.py 責任

`tests/conftest.py` 負責測試前後的全域狀態清理。

應清理：

- cancellation controller。
- memory singleton。
- 環境變數污染。
- 暫存 config path。

應提供：

- `fake_provider`
- `fake_presenter`
- `fake_clipboard`
- `tmp_config_dir`

不得在 unit tests 預設啟動：

- 真實網路。
- 真實 clipboard。
- 真實 keyboard listener。
- 真實 Tkinter mainloop。

## Hotkey 測試重點

Hotkey 是使用者操作上比較脆弱的接縫，必須特別照顧。

Unit / Sims 應測：

- short press 只觸發 short。
- long press 不在 release 時再觸發 short。
- modifier 順序改變仍穩定。
- top-row digits / numpad digits / letters 正確 normalize。
- 多個 action hotkey 彼此隔離。
- 重複 press/release 不造成多次誤觸。

Integration 應測：

- 真實 listener 可註冊與釋放。
- 快速連按不殘留狀態。
- app stop 後 listener 被確實停止。

## Popup 測試重點

Popup 是另一個穩定性重點。

Unit / Sims 應測：

- loading 狀態。
- streaming chunk append。
- finalize result。
- copy/archive/speak button。
- follow-up toggle。
- close session cleanup。
- presenter unsubscribe event。
- selection 優先於 full output。

Integration 應測：

- 真實 button click。
- popup 開啟後 focus 被搶走。
- streaming 中按 copy/speak/archive。
- popup 關閉後 background callback 不造成 crash。
- clipboard restore 在錯誤與取消情境下仍穩定。

## Runtime 與 concurrency 測試重點

- 新 hotkey 取消舊的未 pin session。
- closed/cancelled session 忽略晚到 provider result。
- revision 較舊的 UI update 不可覆蓋新狀態。
- Provider worker 不直接呼叫 Tkinter。
- shutdown 會停止 listener、取消 sessions 並關閉 thread pool。
- 程式生命週期只建立一個 Tk root/mainloop。

## Architecture tests

以 AST 掃描 imports，不額外依賴 lint plugin：

- `core` 不得 import 其他 ClipAI layer。
- `services` 只能 import `core`。
- `platform`、`providers`、`ui` 不得彼此或反向 import `services/app`。
- 只有 `app` 可以同時知道 concrete adapters 與 services。
- 不得存在 global Event Bus 或未設移除期限的 compatibility shim。

## Marker 規則

`integration` marker 表示測試會碰真實外部世界，例如：

- OS clipboard。
- keyboard listener。
- Tkinter/WebView。
- notification。
- TTS/STT。
- 真實 provider 或本機 provider。

預設 pytest 不跑 integration tests。需要明確指定：

```powershell
python -m pytest -m integration
```

`slow` marker 表示測試成本較高，但不一定碰真實外部世界。

## 最終原則

穩定性是 ClipAI 的產品功能。

測試架構不是附屬品，而是架構設計的一部分。每一個新功能都應思考：這個功能的真實世界接縫在哪裡？測試時能不能拔掉？如果不能，代表架構還沒有切乾淨。
