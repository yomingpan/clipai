# ClipAI Preview 安裝與驗收

這是可在本機驗收的 ClipAI 3.7.8 候選版，限定 Windows 11 x64。
最新交付是 [2026-10-04 r4 修正版](../../artifacts/first-install-delivery/ClipAI-Preview-3.7.8-20261004-r4/README.md)，
修正移除完成頁被預設安裝文字覆寫，提供使用中提示；保留 r3 的模型刷新、圖示與桌面捷徑修正。
已安裝 Preview 時，用 r4 Setup 先選保留資料移除，再選安裝；不要直接覆蓋既有安裝。
Setup 自帶 Python 與離線依賴，不需要安裝 Python、Git 或 OpenSSH。
它使用獨立的 ClipAI Preview 目錄與捷徑；使用 AI 時仍需網路及自己的 provider API key。

## 安裝與第一次使用

1. 先從原本 ClipAI 的 Tray 選 **Exit**。目前桌面 runtime 是單一實例，原版與 Preview 不能同時執行。
2. 開啟交付目錄中的 `ClipAI-Preview-3.7.8-Setup.exe`，選 **Install ClipAI Preview**，繼續安裝。不需要以系統管理員身分執行。
3. 等到 **ClipAI Preview installed**。離線 venv 建立需要等待；先看到檔案解壓完成不代表整個安裝成功。
4. 勾選 **Launch ClipAI Preview**，或從 Windows Start Menu 開啟 **ClipAI Preview**。完成頁預設不自動啟動。
5. 找到 Tray 的 ClipAI 圖示，開啟 **Provider Settings...**，選擇你要使用的 provider 並輸入自己的 API key。等到驗證與儲存成功，再選 provider／model。
6. 在記事本輸入 `Hello, this is an installation acceptance test.`，選取整句，按 **Ctrl+Alt+1**（預設翻譯繁體中文）。看到翻譯結果後按 Copy，應有完成回饋，並可貼到記事本。
7. 從 Tray 退出，再由 Start Menu 開啟一次。Provider／model 設定應仍在，不必重新輸入 key。

Setup 未做正式 Authenticode 簽署，Windows 可能顯示未識別發行者或阻擋。
若被系統政策阻擋，記錄畫面與 Windows 版本；不要關閉系統防護來完成驗收。
候選版的官方線上更新流程不列入這次驗收，請用同一個 Setup 做維護。

## 必要驗收

| 操作 | 通過條件 |
| --- | --- |
| 一般使用者安裝 | 不要求管理員／另裝工具；最後才顯示 installed；Start Menu 有 ClipAI Preview |
| 無網路安裝 | Setup 可建立完整環境；provider 請求等恢復網路且明確操作後才開始 |
| 啟動與首次 Action | Tray 可操作；Provider Settings 的驗證／儲存有真實回饋；上述翻譯及 Copy 可完成 |
| 退出後再開啟 | 可啟動，設定及 key 保留 |
| 保留資料卸載／重裝 | 先 Exit，再開同一個 Setup 選 **Remove ClipAI Preview and retain data**；看到 removed。再選 Install 重裝；key／偏好仍在，Action 可用 |
| 重複安裝 | 安裝完成後直接再選 Install，應顯示未完成並保留既有安裝；請先移除再重裝 |
| 使用中卸載 | Tray 還在執行時選移除，應拒絕；Exit 後重試可完成 |
| 取消準備階段（選測） | 準備中按 Cancel，先看到取消等待；工作與清理完成後才顯示取消／失敗，不能顯示 installed。提交階段取消按鈕會停用 |

請回報「失敗在哪一步、畫面訊息、是否仍有 Tray 圖示」。Setup log 在
`%TEMP%\Setup Log *.txt`；本機 ownership／階段證據在 shared 目錄的
`managed-update\transactions\<transaction>\initial-install.json`。
不用提供 API key，也不要傳送 shared 的 `.env`。

## 目錄與驗收範圍

程式：`%LOCALAPPDATA%\Programs\ClipAI Preview`。
資料：`%LOCALAPPDATA%\ClipAI Preview`；key 位於其 `secrets\.env`，卸載預設保留。
舊版/source 的設定不會自動匯入 Preview，第一次需要另外設定。

本機已驗證實際 Setup、空 PATH、完整依賴載入、native 捷徑與登錄、拒絕重複／使用中卸載、損壞 venv 維護及保留資料重裝。
目前原本 ClipAI 仍在執行，桌面啟動探針依單一實例 gate 跳過；你的 Tray／首次真實 AI 結果仍需上表手動驗收。
這不是公開發行完成：正式 publisher 簽署、完整 native license admission、乾淨 VM／重開機、跨 logon session、瀏覽器下載信任及真人新手觀察仍待驗證。
