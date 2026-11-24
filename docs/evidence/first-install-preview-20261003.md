# ClipAI Preview 本機候選驗收

日期：2026-10-03。範圍是 Windows 開發主機的 unsigned local candidate；沒有公開發布。

交付 build：`preview-3d86c9849caf471b8a9666e745d76fe7`，ClipAI 3.7.8。
Setup：34,959,988 bytes（33.34 MiB）。SHA-256：
`19ef4cc62f5187bbd909e8380ae43d930f2e7e5ee02e67d6472366e35231dc7c`。
41 個精確 hash wheels、固定 Python 3.12.14 runtime、private verifier 與 bootstrap packaging。
每次 build 使用獨立本機 manifest authority，私鑰已刪除；無官方 publisher certificate。

## 實際 Setup 驗證

執行的是編譯後的 EXE，以當前一般使用者、預設隔離 Preview root、空 PATH 驗證。
不是只呼叫 synthetic fixture 或直接安裝 wheel。

| 檢查 | 實際結果 |
| --- | --- |
| 安裝 | exit 0，95.62 秒；version／launcher venv、marker、identity selfcheck 通過 |
| 全依賴 loading | main、Tk 建立／update／destroy、pythonnet clr 通過 |
| Windows integration | Start Menu 兩個捷徑及 HKCU uninstall root identity 通過 |
| 重複安裝 | exit 100；原 marker bytes 不變 |
| 使用中卸載 | 自建私有 Python child 存活時 exit 100；原 marker 不變；不終止使用者 process |
| app venv 損壞後維護 | 只將自建 app venv Python rename 為 broken；同一個 Setup 移除 exit 0，17.92 秒 |
| 保留資料重裝 | synthetic shared sentinel bytes 不变；重裝 exit 0，81.05 秒；identity／全依賴／integration 再通過 |
| 最後卸載 | exit 0，18.17 秒；程式 root 與 HKCU uninstall key 消失；shared 資料保留；刪除精確 test sentinel |
| 桌面 runtime 真實啟動 | 探針依現有 desktop instance gate 發現使用者 ClipAI 正在執行，兩次均 skip；沒有冒充通過 |

安裝後程式 logical bytes 為 253,183,484（241.45 MiB），不含 shared staging。
這不是 allocated disk／安裝峰值空間，峰值尚未量測；耗時不是 SLA。
Setup 自帶全依賴且使用 no-index/hash lock，PATH 已清空；未把此當成 NIC 斷網或乾淨 VM 證據。

首次 EXE smoke 發現 Inno `ssPostInstall` 的 RaiseException 仍可讓 native Setup exit 0。
已改為明確 GetCustomSetupExitCode、failed 完成頁及只有 engine 成功才顯示 Launch；上表是修正後 build。
完整 wheel 安裝亦暴露 Bottle RECORD `../../Scripts/bottle.py` 在延伸路徑 sys.prefix 下的 Errno22。
改用 canonical executable argv、保留 filesystem adapter 的 native path 後，完整依賴安裝通過。

## 邊界與回歸

- 既有 unit suite：1,860 passed，46 integration/e2e deselected。
- 新增 native ownership 改變前不得刪除 payload 的 fault test 與 architecture：57 passed。
- 真實 managed-bundle build／offline install／identity-bound launch health integration：1 passed。
- 準備環境已有 venv Python 後送明確 cancel intent：exit 非零、terminal cancelled、owned root 清理、receipt cleaned；通過。
- 同一 canonical root 的 Global gate 跨程序 busy、釋放後 admitted：一般使用者通過。
- 先前中文／空白路徑直接 backend smoke、未知 root sentinel 保留：通過；最終固定路徑 EXE smoke 如上。

可重跑工具：[build／acceptance tools](../../experiments/first_install/README.md)。
原始本機證據位於 `artifacts/first-install-acceptance/final-3d86c9849caf471b8a9666e745d76fe7/`
與 `boundary-e0108ace247f4674a0652a4428692f60/boundary.json`。
交付目錄附 build-evidence.json、acceptance.json、boundary.json 與 SHA256.txt。
當前 Codex packaged-host 的 LOCALAPPDATA 解析可涉及 LocalCache，實際 canonical roots 記錄在 JSON；
不將此開發主機環境當成 Explorer 下載／乾淨 Windows 裝置證據。

## 尚待驗收／發行 gate

現在可依 [安裝與驗收步驟](../specs/first-install-preview-acceptance.md) 做手動 Tray／第一個真實 Action、Copy、退出重啟及 key 保留驗收。
尚未執行 GUI Cancel 點擊、Control Panel maintenance helper 的互動、重開機與 NIC 斷網。
正式 Authenticode publisher、全 native signing／license admission、乾淨 VM、跨 logon session gate、
舊 Local writer 遷移、瀏覽器下載信任、官方更新 feed 與真人新手觀察仍未完成。
Control Panel helper 的暫存副本尚無自動 garbage collection；本次實測維護使用同一個 Setup。
