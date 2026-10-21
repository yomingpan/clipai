# 啟動健康檢查修正實測：3.7.16 → 3.7.17

本次 A／B Setup 的穩定 launcher 都包含 health 預設 120 秒修正；
截止當下仍檢查並驗證健康訊號，準備交接預設維持 600 秒。
真正啟動失敗仍會安全回復；遲到的其他啟動訊號不會被接受為成功。

發布狀態：[Release](https://github.com/yomingpan/clipai/releases/tag/acceptance-20261006-r3)
已於 2026-10-06 10:45:33 +08:00 公開為 prerelease。20 個公開 API
精確資產及真實 catalog discovery 已通過；20 檔匿名完整下載／SHA256
及 B bundle 真實 Ed25519 簽章 admission 全部 passed。下載驗證採有界
ranges／重試，不代替 App 的實際連續下載與完整 About 更新。
兩版 Setup／bundle 的封裝、離線安裝及解包驗證通過；2026-10-06 使用者
確認成功更新至 3.7.17，實機 About 更新 passed（使用者回報）。
見[發布證據](../evidence/github-acceptance-publication-20261006-r3.md)。

1. 從 Tray 退出舊 ClipAI Candidate。在 Windows 移除舊 Candidate，保留設定、
   API key 與資料，不勾選完整資料刪除。不要手動刪除 versions 或替換 keyring。
2. 從本次 Release 下載 `SHA256SUMS.txt`，比對後安裝
   `ClipAI-Candidate-Setup-3.7.16-windows-x64.exe`。確認 About 是 3.7.16，
   然後從 Tray 退出。A／B 共用新的配對公鑰；舊配對的 launcher 不適用。
3. 同頁下載 `launch_isolated_about.py` 到「下載」資料夾，從 Windows「開始」
   開啟一般 PowerShell，執行以下整段：

   ```powershell
   $acceptanceInstall = Join-Path $env:LOCALAPPDATA 'Programs\ClipAI Candidate'
   $acceptanceShared = Join-Path $env:LOCALAPPDATA 'ClipAI Candidate'
   $acceptanceHelper = Join-Path $env:USERPROFILE 'Downloads\launch_isolated_about.py'
   & "$acceptanceInstall\versions\3.7.16\.venv\Scripts\python.exe" -I $acceptanceHelper `
     --install-root $acceptanceInstall --shared-root $acceptanceShared `
     --catalog-url 'https://github.com/yomingpan/clipai/releases/download/acceptance-20261006-r3/catalog.json' `
     --timeout-seconds 600
   ```

   `600` 是驗收 helper 的總存活期限，也是此 helper 接受的上限；
   可接受範圍為 30–600 秒。準備交接等待上限 600 秒、
   每次啟動健康檢查上限 120 秒各有自己的用途。一般捷徑讀正式 latest，
   本次需由 helper 啟動以讀隔離 catalog。
4. 出現 `ISOLATED_ABOUT_READY` 後，開啟 About 並按 Update。
   觀察檢查、下載、準備、舊 App 退出及新 App 重啟。
   冷啟動超過 20 秒可繼續等待；完成後 About 應為 **3.7.17**。
5. 確認原設定保留，從原捷徑重開，方便時重開機再確認。
   若失敗，回報錯誤代碼、仍執行的版本並保留交易證據。

本輪成功須由 3.7.16 的 About 更新到 3.7.17；直接安裝 B Setup
不能取代更新驗收。健康檢查模擬與封裝驗證不等同這台電腦更新成功。
乾淨 VM 仍依使用者指示跳過；本輪為 unsigned technical prerelease。

2026-10-06 執行紀錄：使用者回報「成功了 更新到3.7.17」，本輪 About
更新 passed（使用者回報）。未另外收集起始版本、事件紀錄或 health receipt；
第 5 步的設定保留、捷徑重開及 reboot 尚待個別確認。
