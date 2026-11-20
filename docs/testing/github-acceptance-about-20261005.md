# About 修正候選實測：3.7.10 → 3.7.11

目前：本機封裝及遠端 20 資產精確 hash／bytes 已通過；
[GitHub acceptance-20261005](https://github.com/yomingpan/clipai/releases/tag/acceptance-20261005) 已公開為 prerelease。
20 檔匿名下載／整檔 SHA256、B 真實簽章 admission 都 passed，可以依以下步驟人工測試。
大檔驗證使用 ranges＋有限重試；實際 About 的連續下載與安裝仍待驗收。
舊配對與本配對使用不同一次性 authority；不可改寫已安裝 keyring。

1. 退出 ClipAI Candidate，由你在 Windows 移除舊候選並**保留設定、API key 與資料**。
   不勾選完整資料刪除。自動工具不會移除你的既有安裝。
2. 比對新 SHA256 清單，安裝配對 A `ClipAI-Candidate-Setup-3.7.10-windows-x64.exe`。
   確認 About 為 3.7.10，再從 Tray 退出。
3. 從 Windows「開始」開啟一般 PowerShell。下載新的 helper 後執行：

   ```powershell
   $acceptanceInstall = Join-Path $env:LOCALAPPDATA 'Programs\ClipAI Candidate'
   $acceptanceShared = Join-Path $env:LOCALAPPDATA 'ClipAI Candidate'
   $acceptanceHelper = Join-Path $env:USERPROFILE 'Downloads\launch_isolated_about.py'
   & "$acceptanceInstall\versions\3.7.10\.venv\Scripts\python.exe" -I $acceptanceHelper `
     --install-root $acceptanceInstall --shared-root $acceptanceShared `
     --catalog-url 'https://github.com/yomingpan/clipai/releases/download/acceptance-20261005/catalog.json' `
     --timeout-seconds 600
   ```

   helper 會先檢查實際 shared/update 路徑。若被轉到 declared root 外，停止並提示換一般
   PowerShell；不放寬 containment，也不把設定導到第二套 root。helper 使用已安裝 wheel，
   不會自動點更新或呼叫 provider。
4. 在 About 明確點擊 Update。畫面應依序顯示檢查、下載、準備與重新啟動。
   網路失敗／body deadline 到期應顯示可重試錯誤；退出會取消尚未交接的下載。
5. 成功後確認 3.7.11、既有設定保留，再從原捷徑重開；方便時重開機再確認。
   失敗請回報錯誤代碼與仍可用版本，不刪 versions、設定或 keyring。

檢查與下載有 cooperative deadline，已阻塞 IO 要等 socket timeout，並非硬中斷 OS 呼叫。
簽章與檔案完整性驗證持續生效。實際更新、reboot、VM 與正式簽署檔驗收目前都未記為 passed。

發布與精確驗證見[證據](../evidence/github-acceptance-publication-20261005.md)。

## 已安裝 3.7.10：直接啟動本機驗收 helper

2026-10-05 使用者安裝 3.7.10 從 Tray 按 Update 顯示最新版。唯讀程序確認為
正常 `payload/main.py launch`，不是 helper；同一 discovery 對 production 回傳
None，對本次 acceptance catalog 選到 3.7.11。此時保留既有 3.7.10 安裝，先
Tray → Exit，再從 Windows「開始」開啟一般 PowerShell，貼上以下整段。
本機 helper SHA256 已與公開資產核對，不需要另外下載：

```powershell
$acceptanceInstall = Join-Path $env:LOCALAPPDATA 'Programs\ClipAI Candidate'
$acceptanceShared = Join-Path $env:LOCALAPPDATA 'ClipAI Candidate'
$acceptanceHelper = 'C:\Users\88698\ClipAI_v2.worktrees\next_gen\artifacts\github-acceptance-20261005\launch_isolated_about.py'
& "$acceptanceInstall\versions\3.7.10\.venv\Scripts\python.exe" -I $acceptanceHelper `
  --install-root $acceptanceInstall --shared-root $acceptanceShared `
  --catalog-url 'https://github.com/yomingpan/clipai/releases/download/acceptance-20261005/catalog.json' `
  --timeout-seconds 600
```

看到 `ISOLATED_ABOUT_READY` 後，在這次啟動的 ClipAI 開啟 About 並明確按 Update。
helper 啟動保留目前設定與安裝的信任 keyring；actual About 結果仍 pending。

## 2026-10-06 實測失敗與新修正候選

上述 3.7.10 → 3.7.11 實測在下載後 failed / `identity_ineligible`；
未發出交接 ready，active pointer 保留 3.7.10、revision 0。
根因為 Windows venv 邏輯 executable 與原生行程 image 不同；
詳見[診斷證據](../evidence/about-identity-ineligible-20261006.md)。
舊已公開檔案保持原樣。修正已納入新 3.7.12／3.7.13 配對，
本機驗證通過並經使用者直接授權公開為 `acceptance-20261006`；
使用[新配對步驟](github-acceptance-about-20261006.md)與其發布證據。
不要用重試本配對代替新 launcher 安裝。
