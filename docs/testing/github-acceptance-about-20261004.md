# GitHub About 更新實測：3.7.8 → 3.7.9

這份步驟用於已公開的 [acceptance-20261004 測試版](https://github.com/yomingpan/clipai/releases/tag/acceptance-20261004)。
它是未做 Windows publisher 簽章的 ClipAI Candidate；乾淨 VM 已依使用者指示暫緩。
本輪要取得的是開發電腦上的實際 About 更新證據。

**本次 A 透過一般捷徑啟動時，About 仍查正式 `latest`；該來源目前沒有本次 B，
所以 3.7.8 會顯示「目前已是最新版本」。必須依第 4 步用隔離 helper 啟動，
才會查 `acceptance-20261004/catalog.json` 並找到 3.7.9。**
這是候選驗收啟動方式；正式使用者的發行流程仍使用正式 `latest`。

1. 下載該頁的 `ClipAI-Candidate-Setup-3.7.8-windows-x64.exe`（A）、
   `launch_isolated_about.py` 與 `SHA256SUMS.txt`。更新會透過 HTTPS 下載 B，
   不需先安裝 3.7.9。若只想測試新版安裝，才直接下載 3.7.9 Setup。
2. 比對下載檔與 SHA256 清單。A Setup hash：
   `961704178b9a10a160cf27fa0562695a5602eee036bc30319183feec2d4da391`。
   `launch_isolated_about.py` 的 hash 也必須相符。
3. 退出目前的 ClipAI Candidate。如果已裝舊候選，由你在 Windows「已安裝的應用程式」
   移除 **ClipAI Candidate**，保留資料（不要勾選刪除設定／API key／資料），再安裝
   本次配對的 A。舊候選與本次 A／B 的更新信任金鑰不同，不能只替換 keyring。
   此步驟需你明確選擇；自動工具沒有移除既有安裝或改寫設定。
4. 確認 About 顯示 3.7.8，接著從 Tray 退出，避免同時開兩個程式。
   在 PowerShell 使用 A 安裝的 Python 啟動隔離測試來源：

   ```powershell
   $acceptanceInstall = Join-Path $env:LOCALAPPDATA 'Programs\ClipAI Candidate'
   $acceptanceShared = Join-Path $env:LOCALAPPDATA 'ClipAI Candidate'
   $acceptanceHelper = Join-Path $env:USERPROFILE 'Downloads\launch_isolated_about.py'
   & "$acceptanceInstall\versions\3.7.8\.venv\Scripts\python.exe" -I $acceptanceHelper `
     --install-root $acceptanceInstall --shared-root $acceptanceShared `
     --catalog-url 'https://github.com/yomingpan/clipai/releases/download/acceptance-20261004/catalog.json' `
     --timeout-seconds 600
   ```

   若下載存到其他資料夾，將 `$acceptanceHelper` 改成實際路徑。此工具使用已安裝
   wheel 與既有信任驗證，不會自動點更新、呼叫 provider 或修改正式 latest。
   它最長等待 10 分鐘；逾時可用同一指令重新開始。
5. 由你在 About 點擊 Update，觀察檢查、下載、準備、重新啟動的結果。
   成功後確認 About 顯示 **3.7.9**，既有 provider／設定仍保留，程式能正常啟動。
   本次公開 B bundle hash：
   `47f08a74912c5130a41c50dff22e3a5b298070856ee37078b30b7a83b6f7d2eb`，
   與 Setup B 內含的 bundle 相同。
6. 退出並從原捷徑重開，確認仍是 3.7.9；方便時重開機再確認。
   回報更新前後版本、設定是否保留、捷徑重開／重開機是否正常。失敗則記錄 UI
   顯示的錯誤與目前仍可用的版本，保留資料供定位，不手動刪除 versions 或 keyring。

實際 About 更新、重開機與 provider Action 尚待人工回報，不能以下載或簽章驗證
代替。真實故障回復／跨 logon／新手首次結果及正式簽章仍是獨立驗收項目。
