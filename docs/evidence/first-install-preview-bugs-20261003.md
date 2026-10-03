# Preview 驗收問題：console 與 Gemini 驗證

日期：2026-10-03。使用者回報黑色 command 視窗與 Gemini key 被拒絕，原版同 key 仍成功。

## 判斷與觀察

Console：已重現並鎖定。Installed private version venv 透過真實
`start_detached_process` 啟動只讀 GetConsoleWindow 的測試程序，python.exe
回報 console_present=true；同 executable 改 CREATE_NO_WINDOW 時 false。
採 local fix，以 CREATE_NEW_PROCESS_GROUP + CREATE_NO_WINDOW 取代
DETACHED_PROCESS，保留 python.exe 的 executable／startup-health identity。
不增加另一個啟動 policy 或改以 pythonw 繞過既有 identity 驗證。

Gemini：使用專案已保存的 credential，source HTTP Models 取得 HTTP 200、50 models；
已安裝 Preview 的真實 catalog adapter 取得 44 個 generateContent models。
沒有輸出 key、原始 error body 或 credential-bearing environment。
這證明該 credential 在測試環境可用，尚不能證明使用者於設定視窗送出的
credential／provider／網路環境完全相同。使用者實際 auth failure 尚未重現，
不能把錯誤分類改善宣稱為已修好他的 key 問題。

另觀察到 Preview launcher 的錯誤對話框「startup health timed out」。
使用者退出所有 app 後，installed desktop startup probe 通過
DESKTOP_RUNTIME_READY 與 DESKTOP_TYPED_SHUTDOWN_COMPLETED。
先前 timeout 與單一實例衝突可能相關，仍以完整 managed launch health 檢查確認，
不僅憑 import 或顯示 Tray 判定成功。

## 錯誤規則的邊界診斷

分類 Yellow，推薦局部重構，信心高：catalog 與 Gemini execution 各自把
401/403 都視為無效 key，會將 API restriction／project permission 誤報為 authentication。
保留驗證失敗不保存／不啟用 credential 的行為。

1. 唯一 owner：Google HTTP error 語義由 Gemini adapter 擁有；services 擁有設定
   mutation 與安全結果投影，UI 僅呈現。沒有新增 state owner。
2. 可重用能力：同一 provider 的 catalog／generation 要共用錯誤分類，不是 Setup 特例。
3. 洩漏：若把 Google reason 分支放進 UI 或 services，會讓外層依賴 provider-specific payload。
4. 防護：共用 `gemini_errors.py`；只允許固定 reason 白名單及固定說明，未知 reason／message
   不回顯；401／明確 invalid/expired key 仍 AuthError，403 permission 是 ResponseError。

Debt multiplier：兩份 HTTP 規則若再加入 restriction、leaked key、billing failure，
每次修正都要修改兩处，且 message 可能洩漏 key。接受現況便宜但誤導使用者；
UI 特例增加耦合；全面 transport 重寫成本過高。選 adapter 局部共用，易回退。
順序：建立三個 red regression tests → 局部修正 → targeted/architecture → unit →
native console／installed adapter／managed launch smoke → 新候選 Setup。

簡短 ADR：保留現在 transport 與 core exceptions；Gemini adapter 收斂 status 解釋，
拒絕回顯任意 server body。不引入另一套 diagnostics 或 validation coordinator。
代價是未知 Google failure 的提示較概括；新增已證實 reason 時才擴充白名單。
Review trigger：第二個 provider 需要同樣 structured-error capability 時，重新檢查邊界。

## 證據與剩餘問題

Red command：
`scripts/run_unit_tests.py -- tests/platform/test_managed_update_lifecycle.py::test_desktop_launch_uses_no_window_without_detached_console tests/providers/test_model_catalog.py::test_gemini_permission_denial_is_not_reported_as_invalid_key tests/providers/test_model_catalog.py::test_gemini_unknown_permission_denial_does_not_echo_response_or_untrusted_reason -q`
修正前 3 failed；修正後針對性 provider／lifecycle／settings／architecture 101 passed。
完整 native probes 存於 artifacts/first-install-diagnostic。
沒有長期 debug instrumentation，也沒有自動複製 credential 至 Preview。

Google 來源：[Gemini troubleshooting](https://ai.google.dev/gemini-api/docs/troubleshooting)、
[API key troubleshooting](https://cloud.google.com/api-keys/docs/troubleshooting)。
下一個高價值證據是新版 Provider Settings 明確選 Gemini 後的驗證結果；
若仍拒絕，只回報安全分類與 HTTP code／白名單 reason，不要求 API key。

## r2 交付與完成證據

Build：`preview-4c5b4941f25e4cb8973bbdda0672b481`。
SHA-256：`62c27c334b4b8989bad0bfb4c52eaa882043a7cf9fb9542495fc5665f3449718`。
交付目錄：`artifacts/first-install-delivery/ClipAI-Preview-3.7.8-20261003-r2`。
沒有覆寫 r1 Setup 或使用者既有 Preview 安裝。

- 完整 unit：1,867 passed，46 deselected；真實 managed-bundle integration：1 passed。
- 新候選獨立 Verification root 的完整離線 bundle 安裝通過。
- `managed_desktop_probe.py` 使用同一 admission／manifest／real desktop／health channel，
  在 ready boundary 回報 console_present=false、identity_bound_health=passed，
  再以 typed Shutdown 正常退出。原始 user root 在 Codex packaged-host 下的先前
  probe 觸發 containment guard（path escapes managed root），沒有放寬 guard；
  最終裝置證據使用工作區內完全隔離 root，避免該 host AppData virtualization。
- 新候選真實 Provider Settings use case 以已保存 Gemini credential 驗證成功、
  active_provider=gemini。Persistence 由完整 memory-store double 接住，沒有 secret 落盤。
- 專屬 Verification 程式／native integration 已移除，shared 診斷證據保留。

本次 r2 未再將同一固定 root 的 EXE 安裝於使用者目前 Preview 上，以免更動現有資料或
混用 packaged-host 與 Explorer 的 AppData 路徑。Setup 腳本未改，r1 native EXE 安裝／
卸載／重裝證據仍獨立保留；r2 編譯包與完整新 bundle 的診斷證據如上。
新版實際 UI 與翻譯驗收仍待使用者重試，不宣稱「key 已修好」。

後續比對發現：原版 repository 的 `.env` 與目前 worktree 保存的 Gemini key 不同。
上述 HTTP 200／catalog／settings 成功全部使用 worktree credential，不是原版 repository
那把 credential 的證據。沒有輸出兩把 key 或 hash，只確認是否相同。
對原版 repository credential 的首次 Models API 驗證被自動核准審查拒絕：
跨私有 repository 的 credential 外送需使用者明確授權；沒有繞過。
使用者隨後明確允許讀取 `C:\Users\88698\ClipAI_v2\.env` 的 GEMINI_API_KEY，
向 Google 官方 Models API 做一次唯讀驗證。授權後僅執行一次，回傳 HTTP 403、
PERMISSION_DENIED，已知 leaked-key 訊息判定為 true；沒有產生 AI 內容，
沒有輸出／另存 key 或原始 response。這證實原版檔案保存的 key 遭 Google 封鎖，
不能推論外洩來源，也不能證明原版執行中的記憶體使用同一把 key。
需由使用者在 Google AI Studio 建立替代 key，再在 r2 Provider Settings 驗證。
r2 已包含固定 leaked-key 提示；另補 catalog 回歸測試，確認替代指引與不回顯 server text。
