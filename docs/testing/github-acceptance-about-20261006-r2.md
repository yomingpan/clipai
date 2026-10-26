# 交接準備期限修正實測：3.7.14 → 3.7.15

本次候選的 App 準備交接等待預設為 600 秒。原始 20 秒／78 秒問題已由
模擬時鐘回歸測試重現並修正。使用者實測已確認交接成功，但後續
`health_timeout` 導致回復 3.7.14；本配對的完整 About 更新 gate 為 failed。
這組不可變候選仍使用 20 秒 health 預設，工作區後續修正不會改變它們。
見[健康檢查診斷](../evidence/about-health-timeout-20261006.md)。

發布狀態：[acceptance-20261006-r2](https://github.com/yomingpan/clipai/releases/tag/acceptance-20261006-r2)
已公開為 prerelease，20 個 API 精確檔案 identity 與 catalog discovery passed；
20 檔匿名整檔下載／SHA256 及 B signature admission 亦全部 passed。
下載驗證採有界 ranges／重試，不代替實際 About 更新。
見[發布證據](../evidence/github-acceptance-publication-20261006-r2.md)。

1. 從 Tray 退出舊 ClipAI Candidate。在 Windows 移除舊 Candidate，保留設定、
   API key 與資料，不勾選完整資料刪除。不要手動刪除 versions 或替換 keyring。
2. 從本次 Release 下載 `SHA256SUMS.txt`，比對後安裝
   `ClipAI-Candidate-Setup-3.7.14-windows-x64.exe`。確認 About 是 3.7.14，
   然後從 Tray 退出。新 A／B 共用新的配對信任公鑰，舊配對不適用。
3. 同頁下載 `launch_isolated_about.py` 到「下載」資料夾，從 Windows「開始」
   開啟一般 PowerShell，執行以下整段：

   ```powershell
   $acceptanceInstall = Join-Path $env:LOCALAPPDATA 'Programs\ClipAI Candidate'
   $acceptanceShared = Join-Path $env:LOCALAPPDATA 'ClipAI Candidate'
   $acceptanceHelper = Join-Path $env:USERPROFILE 'Downloads\launch_isolated_about.py'
   & "$acceptanceInstall\versions\3.7.14\.venv\Scripts\python.exe" -I $acceptanceHelper `
     --install-root $acceptanceInstall --shared-root $acceptanceShared `
     --catalog-url 'https://github.com/yomingpan/clipai/releases/download/acceptance-20261006-r2/catalog.json' `
     --timeout-seconds 1200
   ```

   `1200` 是隔離驗收 helper 的總存活期限，包含人工操作、下載與準備；
   App 的 host 準備等待上限是 600 秒。一般捷徑仍讀正式 latest；
   本次測試需由 helper 啟動以讀取隔離 catalog。
4. 出現 `ISOLATED_ABOUT_READY` 後，開啟 About 並按 Update。
   觀察檢查、下載、準備、舊 App 退出及新 App 重啟。
   準備可能超過 20 秒，應繼續等待；成功後 About 應為 **3.7.15**。
5. 確認原設定保留，從原捷徑重開，方便時重開機再確認。
   若失敗，回報錯誤代碼與仍執行的版本，保留交易證據。

測試不得以 B Setup 直接安裝取代 A 的 About 更新驗收。
乾淨 VM 與正式 Windows publisher 簽章仍未通過。
