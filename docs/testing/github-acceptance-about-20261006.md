# Windows venv 身分修正實測：3.7.12 → 3.7.13

狀態：[acceptance-20261006](https://github.com/yomingpan/clipai/releases/tag/acceptance-20261006)
已公開為 prerelease；遠端 20 個資產的精確 bytes／SHA256 與 catalog discovery passed。
20 檔匿名整檔下載／SHA256 與 B 真實簽章 admission 全部 passed，可以依下列步驟實測。
大檔驗證有界 ranges／重試。後續使用者在另一台電腦實測：App 在 20 秒
`handoff_timeout`，host 到 78 秒才 ready，之後 `shutdown_failed`。
這份已公開配對尚未包含準備期限修正，不應作為修正版驗收。
見[交接期限診斷](../evidence/about-handoff-timeout-20261006.md)。
3.7.10 → 3.7.11 實測在 `identity_ineligible` 失敗；舊 stable launcher
不會透過 B bundle 自行取得本次修正。請使用新配對 A Setup。

匿名下載及簽章驗證見[發布證據](../evidence/github-acceptance-publication-20261006.md)。

1. 從 Tray 退出 ClipAI Candidate。在 Windows 移除舊 Candidate，**保留設定、
   API key 與資料**，不要勾選完整資料刪除。
2. 比對 `SHA256SUMS.txt`，安裝 `ClipAI-Candidate-Setup-3.7.12-windows-x64.exe`。
   確認 About 為 3.7.12，再從 Tray 退出。新配對使用新的信任 authority，
   不手動改寫已安裝 keyring。
3. 從 Windows「開始」開啟一般 PowerShell。下載本次 helper 後執行：

   ```powershell
   $acceptanceInstall = Join-Path $env:LOCALAPPDATA 'Programs\ClipAI Candidate'
   $acceptanceShared = Join-Path $env:LOCALAPPDATA 'ClipAI Candidate'
   $acceptanceHelper = Join-Path $env:USERPROFILE 'Downloads\launch_isolated_about.py'
   & "$acceptanceInstall\versions\3.7.12\.venv\Scripts\python.exe" -I $acceptanceHelper `
     --install-root $acceptanceInstall --shared-root $acceptanceShared `
     --catalog-url 'https://github.com/yomingpan/clipai/releases/download/acceptance-20261006/catalog.json' `
     --timeout-seconds 600
   ```

   若 helper 提示 shared/update 路徑重導，停止並改用一般 PowerShell。
   它不自動更新或呼叫 provider。正常捷徑仍使用正式 latest，不能代替此隔離測試。
4. 看到 `ISOLATED_ABOUT_READY` 後，開啟 About 並明確按 Update。
   觀察檢查、下載、準備及重啟；成功後應為 **3.7.13**，原設定保留。
5. 從原捷徑重開；方便時重開機再確認。失敗回報錯誤代碼及仍可使用的版本，
   保留交易證據，不刪 versions、設定或 keyring。

本機 unit、原生 Windows 行程與封裝驗證分別記錄於
[診斷證據](../evidence/about-identity-ineligible-20261006.md)。
實際 About 更新、reboot、故障回復、新手及乾淨 VM 驗收仍 pending；
正式 Windows publisher 簽章仍未通過。

## 此電腦的本機 helper

本次工作區已備妥與發布檔案相同 SHA256 的 helper。
安裝 3.7.12 並從 Tray 退出後，可在 Windows「開始」開啟的一般 PowerShell
直接貼上以下整段，不需要另外下載 helper：

```powershell
$acceptanceInstall = Join-Path $env:LOCALAPPDATA 'Programs\ClipAI Candidate'
$acceptanceShared = Join-Path $env:LOCALAPPDATA 'ClipAI Candidate'
$acceptanceHelper = 'C:\Users\88698\ClipAI_v2.worktrees\next_gen\artifacts\github-acceptance-20261006\launch_isolated_about.py'
& "$acceptanceInstall\versions\3.7.12\.venv\Scripts\python.exe" -I $acceptanceHelper `
  --install-root $acceptanceInstall --shared-root $acceptanceShared `
  --catalog-url 'https://github.com/yomingpan/clipai/releases/download/acceptance-20261006/catalog.json' `
  --timeout-seconds 600
```

看到 `ISOLATED_ABOUT_READY` 後開啟 About，明確按 Update。
helper 不寫入另一套設定／keyring，不自動停止既有 app 或點更新。
