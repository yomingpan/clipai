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

Voice Draft 的細部規則以 `services/voice_draft.py` 的 pure interface 為主要測試面：涵蓋 insertion、revision/frozen target guard、terminal result 套用與 Action/Back transition。`WorkflowController` 只保留少量 integration-style unit tests，驗證它在既有 lock scope 內套用 transition、更新唯一 snapshot、render projection 與維持 navigation 契約。新增案例應補在規則真正所屬的層，不得在 controller tests 再複製一套相同 rule matrix。

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

目前結構：

```text
tests/
  conftest.py
  app/
  architecture/
  core/
  platform/
  providers/
  services/
  support/
  ui/
```

Unit、sim 與 integration tests 依被測 layer 共置；會接觸真實外部世界的
case 以 `integration` marker 區分，不另建一套與 layer 重複的目錄樹。共用
fake 優先放在最小可見範圍，只有跨多個 test module 使用時才提升至
`tests/conftest.py` 或明確的 helper module。

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
- `FocusEntered` 必須具名攜帶 native foreground 與 toolkit focus；兩軸皆真
  才能通過 initial-focus gate。
- Alt+Tab、taskbar switch 與 external foreground theft 必須透過獨立事實
  釋放 focus，且 Paste/owned dialog guard 不得被繞過。手動矩陣見
  `docs/testing/popup-focus-manual-checklist.md`。

### Paste Operation 測試矩陣

Service 與 runtime sims 必須覆蓋以下 dispatch × cleanup × cancellation
矩陣：

| 時機／條件 | Delivery | Cleanup | Terminal acknowledgement |
| --- | --- | --- | --- |
| global single-flight admission rejected | `not_dispatched` | `not_required` | `failed` |
| worker 執行前取消或 submit 失敗 | `not_dispatched` | `not_required` | `cancelled` 或 `failed` |
| fail-closed preservation 拒絕原生格式 | `not_dispatched` | `not_required` | `failed` |
| clipboard mutation 後、dispatch gate 前取消 | `not_dispatched` | `restored` | `cancelled` |
| dispatch 後成功恢復 | `dispatched_unconfirmed` | `restored` | `dispatched_unconfirmed` |
| dispatch 後發現 external clipboard change | `dispatched_unconfirmed` | `external_change` | `dispatched_unconfirmed` |
| dispatch 後恢復失敗 | `dispatched_unconfirmed` | `failed` | `cleanup_failed` |
| mutation 後、尚未 dispatch 即恢復失敗 | `not_dispatched` | `failed` | `cleanup_failed` |
| dispatch 後才收到取消 | 保留既有 dispatch truth | 實際 cleanup truth | 不得降級為 `cancelled` 或 `failed` |

另外必須驗證：

- container-wide single-flight；重疊請求明確失敗，不排隊、不取代。
- worker 前取消回報 `cancelled / not_dispatched`，且 cleanup 後恰好一次完成。
- worker 中取消等待真實 cleanup 與 dispatch outcome，不提早釋放 membership。
- dispatch 後只有 `dispatched_unconfirmed` 或 `cleanup_failed`，不得出現
  Paste `succeeded`。
- completion 只經 typed `PasteOperationCompleted` command 回到 runtime。
- `PasteOperationCompleted` 與其他 output acknowledgements 保持 ordered、
  exactly-once，且不得進入可 coalesce 的 Workflow snapshot mailbox。
- runtime 不持有 concrete Paste handle 或 `_paste_jobs` registry；architecture
  test 必須防止這個 ownership 退化。
- stale、重複或晚到 completion 不得完成較新的 output operation。
- `TaskSupervisor.submit()` 拒絕工作時，pending 必須立即接 terminal
  acknowledgement，且 interruption plan 不得殘留 phantom operation。
- tracker/presenter 拋錯時，matching、replaced 與 cancel-all records 的 lease
  仍須釋放；stale settlement 不得碰 handle 或 lease。
- Popup outcome/focus matrix 與 `docs/specs/paste-target-focus-adr.md` 一致。

Windows integration smoke 必須覆蓋 clipboard snapshot、temporary text、
conditional restoration 與 external clipboard change；它驗證 adapter seam，
不把 input injection 當成目標程式已消費內容的證明。

### Canonical selection 與 presentation 測試

- 外部 text-capable Action 在 trigger time 擷取 selection；有效 selection
  優先於 clipboard image 與 clipboard text。
- Popup output action 的明確 selection 優先於 displayed step canonical
  content；沒有 selection 才 fallback，且 typed command 攜帶 semantic text。
- Copy、Paste、Archive、Speech 共用 canonical source，不從 styled widget 或
  presentation text 反推內容。
- Markdown parser 保留 canonical fragments；unsupported syntax 安全降級為
  plain text，不遺失 canonical content。
- Selection Capture 與 Paste 共用 clipboard transaction owner；late restore
  不得覆寫使用者或較新的 operation 所做的 clipboard change。
- 九個 `PasteFailureReason` 都必須有 detection-path 測試；reason 由 typed
  error 傳遞，不得從訊息比對推回，且任兩 reason 不得共用同一句使用者訊息。
- Paste `failed`／`cancelled` 必須在 transaction 與 active membership 釋放後
  將 canonical result 保留到 clipboard，並明示可手動 Ctrl+V。
  `dispatched_unconfirmed`／`cleanup_failed` 必須逐位元保留原 clipboard，
  不得因 convenience fallback 製造重複貼上的風險。

### Physical-key release 測試

- 每個完整 shortcut match 建立獨立 press identity，直到 non-modifier
  function key release 或明確 cancellation 才結束。
- Release 必須能以 physical／virtual-key identity 對應原 press；modifier
  持續按住時，下一次 function-key press 仍建立新 identity。
- Long-press deadline 必須重新檢查 physical key state；已放開的 action key
  不得被 late timer 誤判為 long press。
- Missing release 的 stale recovery、listener shutdown 與 injected key events
  不得產生第二次 terminal outcome 或污染下一個 press。

### Voice WebView 可見性量測

- Native seam double 必須保留 `System.IntPtr` 的 `ToInt64()` 契約，且只記錄
  Win32/WinForms 請求；不得把 fake 的綠燈當成 Windows compositor 證據。
- `prepare`、`start`、realisation failure 與 UI-thread/direct execution 由快速
  unit tests 覆蓋。
- 發版前在互動式 Windows desktop 以 `scripts/app_flash_watch.py` 每 20 ms
  取樣目標行程全部 visible top-level windows；每個候選策略至少四次，記錄
  samples、visible frames、opaque frames 與最終 layered/visibility 狀態。

Recipe 回饋與使用引導應測：

- Popup 原始尺寸與結果區高度不因契約、回饋或 coachmark 縮小。
- `ⓘ` Tooltip 固定呈現「AI 幫你」與「AI 不做什麼」，並提示結果不符合預期時可按右上角 `ⓘ` 或 `Ctrl+R` 回饋。
- Ctrl+R 僅作用於聚焦的 Popup；不支援的 Recipe 必須顯示明確狀態。
- 正負案例都只有在使用者明確勾選時保存原文與結果。
- 回饋 pending、成功、失敗與重試反映真實 operation identity。
- 每個 `start_action` Shortcut 的短按與長按 resolved Action 都必須有完整回饋契約；非 Action Shortcut 必須明確列為例外。
- 不同任務的 press variant 必須能覆寫回饋契約，且契約內容納入 Action version。
- 首次提示預設關閉，Tray toggle 預設未勾選；使用者明確開啟後，每個 Action／press type 只顯示一次，重啟後仍保留 seen 狀態。
- Tray checked state 只能在原子保存成功後改變；保存失敗維持舊值。
- 重新顯示所有提示只清空 seen Action，不改變全域開關。

## Runtime 與 concurrency 測試重點

- 單一主要 Popup invariant：新外部 Action 取消舊的未 pin visible Workflow；pinned Workflow 會阻擋第二個主要 Popup，但所有 visible Action shortcut 必須重用既有 pinned Workflow 與同一個 Popup，保留 pinned 狀態並以新 invocation 取代舊 invocation。`Ctrl+Alt+W` 在 active Voice capture 時繼續既有 capture；聚焦的 Voice Review 延續 Draft，聚焦的 completed result 立即展開既有 Follow-up 欄位並把 terminal speech 插入 live caret、不得自動送出。Provider active、Follow-up unavailable 或 visible Popup 未聚焦時必須明確拒絕，不得偷換成新的 Voice Draft；只有沒有 visible Popup 時才建立新的 Voice Draft。
- Voice capture 不以外部 editable target 為啟動前置條件；沒有 target 時仍須建立 targetless Voice Draft，只有使用者明確執行 Paste 時才解析最新 target，解析失敗則顯示 Paste failure。
- Popup waveform 只呈現 engine 回報的 normalized audio level；未收到音量時保持靜止，不以 timer 製造假波形。至少覆蓋 idle、listening、silence hint、finalizing、capability unavailable 與 provider active disabled 狀態。
- Popup follow-up capture 的 terminal result 只在 Workflow identity 與 capture identity 都相符時插入目前游標；不得自動送出，舊 capture 的 completion／failure 不得清除或覆蓋較新的 capture。
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
- `platform/` 之外不得 import `ctypes`、`win32api`、`win32con`、`win32gui`
  或 `winreg`；此規則使用獨立 AST test，讓錯誤直接指出 native owner。
- `ui/` 不得出現 `sys.platform` 或 `windll`。Native-window doubles 只記錄
  contract request，Headless adapter 必須回傳保守結果，不模擬 Windows。

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
