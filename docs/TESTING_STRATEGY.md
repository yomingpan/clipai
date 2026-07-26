# ClipAI 測試架構策略

本文件定義 ClipAI 的測試哲學與測試分層。

核心思想：

> 可測試性就是架構預留的插頭。

ClipAI 一開始就要把系統切成幾個好替換的接縫。像家電插頭一樣，要測試時能把真實世界那些麻煩的東西先拔掉，換成假的來跑。這樣核心邏輯就能很快、很穩地驗證。

## 測試成功來自架構接縫

測試的成功來自 Clean Architecture / Onion Architecture。

業務邏輯只依賴抽象介面，例如：

- `LLMProvider`
- `ApplicationView` / `ResultPresenter`
- typed command queue
- `WorkflowController`（包含 invocation identity、cancellation 與 successful-step history）
- `WorkflowRuntimeModule`（包含 Workflow membership、Foreground Workflow、visible/headless lifetime 與 captured provider binding）
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
    providers/
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
- 已取消但排程中的舊 timer callback 不得完成新的 gesture operation。
- listener stop 必須取消 active timers、清除 dispatcher state，並使 late
  keyboard/timer callbacks 保持無效。

Integration 應測：

- 真實 listener 可註冊與釋放。
- 快速連按不殘留狀態。
- app stop 後 listener、dispatcher state 與 active timers 被確實停止，
  且不得再 enqueue Shortcut intent。

## Popup 測試重點

Popup 是另一個穩定性重點。

Unit / Sims 應測：

- loading 狀態。
- streaming chunk append。
- finalize result。
- copy/archive/speak button。
- follow-up toggle。
- close Workflow cleanup。
- presenter unsubscribe event。
- selection 優先於 full output。

Integration 應測：

- 真實 button click。
- popup 開啟後 focus 被搶走。
- streaming 中按 copy/speak/archive。
- popup 關閉後 background callback 不造成 crash。
- clipboard restore 在錯誤與取消情境下仍穩定。

Recipe 回饋與使用引導應測：

- Popup 原始尺寸與結果區高度不因契約、回饋或 coachmark 縮小。
- `ⓘ` Tooltip 固定呈現 AI 幫你、你仍保留、結果後確認與 Ctrl+R。
- Ctrl+R 僅作用於聚焦的 Popup；不支援的 Recipe 必須顯示明確狀態。
- 正負案例都只有在使用者明確勾選時保存原文與結果。
- 回饋 pending、成功、失敗與重試反映真實 operation identity。
- 每個 `start_action` Shortcut 的短按與長按 resolved Action 都必須有完整回饋契約；非 Action Shortcut 必須明確列為例外。
- 不同任務的 press variant 必須能覆寫回饋契約，且契約內容納入 Action version。
- 首次提示預設開啟、每個 Action／press type 只顯示一次，重啟後仍保留 seen 狀態。
- Tray checked state 只能在原子保存成功後改變；保存失敗維持舊值。
- 重新顯示所有提示只清空 seen Action，不改變全域開關。

## Runtime 與 concurrency 測試重點

- 新的外部 Action 取消舊的未 pin visible Workflow；pinned Workflow 保留但不自動成為 Foreground Workflow。
- visible 與 headless Workflow 使用相同 identity／registration 規則；headless Workflow 不得成為 Foreground Workflow，也不得被強制成全域 singleton。
- close/cancel 釋放 Workflow membership；visible completion 保留 membership 供 follow-up，headless completion 立即釋放。
- Workflow 在建立時 capture provider/model binding；後續 configuration change 不得改變既有 Workflow 的 binding。
- 被取代 invocation 的晚到 provider result 由 active invocation ID 與 cancellation token 拒絕。
- revision 較舊的 Workflow snapshot projection 不可覆蓋較新的 UI 狀態；revision 不得作為 provider invocation 或 output-operation identity。
- Worker completion 與 failure 必須先透過 typed command 回到 runtime，再修改 Workflow lifetime state。
- Provider worker 不直接呼叫 Tkinter。
- shutdown 會停止 listener、取消 Workflows 並關閉 thread pool。
- 程式生命週期只建立一個 Tk root/mainloop。

## Architecture tests

以 AST 掃描 package-qualified imports，不額外依賴 lint plugin：

- `core` 不得 import 其他 ClipAI layer。
- `services` 只能 import `core`。
- `platform`、`providers`、`ui` 不得彼此或反向 import `services/app`。
- 只有 `app` 可以同時知道 concrete adapters 與 services。
- `app/container.py` 是 assembly entry point；runtime provider rebuild 可位於 focused app composition adapter，但不得下沉到 `services` 或 `providers`。
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
