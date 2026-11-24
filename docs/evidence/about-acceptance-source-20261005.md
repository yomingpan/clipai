# 3.7.8 About 顯示最新版：更新來源驗證

日期：2026-10-05，Asia/Taipei。開發電腦、實際 GitHub HTTPS、唯讀 discovery。

使用者回報配對 A 的 About Update 顯示「目前已是最新版本」。目前程序命令屬於
`main.py` 正常啟動，不是 `launch_isolated_about.py`。正常啟動的 composition 使用
`PRODUCTION_MANAGED_UPDATE_CATALOG_URL`；本輪 B 發布於獨立 acceptance release。

使用同一 `HttpsManagedReleaseSource.discover(installed_version='3.7.8',
launcher_version='3.7.8')` 與 `UrllibManagedUpdateTransport(catalog_timeout_sec=15)`：

| catalog URL | 實際選擇結果 |
| --- | --- |
| `https://github.com/yomingpan/clipai/releases/latest/download/catalog.json` | `None`，對應 `up_to_date`；要求找到 3.7.9 的 probe assertion 為紅 |
| `https://github.com/yomingpan/clipai/releases/download/acceptance-20261004/catalog.json` | 3.7.9；同一 assertion 通過 |

差異只有 catalog URL，未下載 bundle 或觸發更新。這是來源不一致，不是版本比較
把 3.7.9 判成較舊。前一則給使用者的簡略操作說明漏掉必要的隔離啟動；runbook
已強調先 Exit，再用第 4 步的 helper 啟動。

唯讀確認目前安裝 current_version 為 3.7.8、product 為 ClipAI Candidate，
launcher 的公共 trust keyring 與已發布配對 A/B 完全相同。helper SHA-256 為
`c6c8b227b812b1cf730b895d8d4b21f1207aa8672d64bd57e71c71d8431eb65e`，
與該 release 的 SHA256SUMS 相符。沒有讀取 credential、改 keyring、改正式
catalog、替換公開資產、停止當前程序或自動點擊更新。

使用者回覆「已退出」後，實際 idle gate 通過。再次驗證 helper hash 與安裝公共
keyring，以已安裝 3.7.8 venv Python `-I` 啟動；使用 acceptance catalog 與 600 秒
attended timeout。helper 已輸出 `ISOLATED_ABOUT_READY: click About Update explicitly`，
故隔離啟動記為 passed。session metadata 在
`artifacts/about-acceptance-20261005/run-d5dcfa60100d4d119fbf0eb9ab94fef2/session.json`。

下一步由使用者在 About 明確點擊 Update。實際 A→B、設定保留、捷徑重開與 reboot
仍 pending；不能把 discovery 或 helper ready 當成更新安裝成功。
後續使用者回報持續檢查：已確認兩筆 bundle 下載及 packaged-app 路徑轉向，
交接仍未完成；見 [下載卡住診斷](about-download-stall-20261005.md)。
production latest 與已公開資產未變更。

## 3.7.10 同一來源差異再次確認

使用者安裝新 A 後從 Tray 點 Update，畫面版本為 3.7.10 並顯示最新版。
唯讀 Win32_Process 確認程序 32708／17528 由已安裝 3.7.10 的
`payload/main.py launch` 正常啟動，沒有 `launch_isolated_about.py`；未停止程序。
Downloads 的 helper 尚不存在，但工作區公開資產的 helper SHA256 與已發布清單一致。

同一實際 `HttpsManagedReleaseSource.discover(installed_version='3.7.10',
launcher_version='3.7.10')`，只改 URL 的最小 differential probe 結果：

```text
normal selected= None expect_3.7.11= False
acceptance selected= 3.7.11 expect_3.7.11= True
```

此 probe 對「正常來源應找到測試 B」為紅，對指定測試 URL 為綠；沒有下載 bundle
或操作使用者安裝。原因仍是測試啟動來源，不是 public catalog 缺 B。
已補上只需 Exit＋一段貼上的本機 helper 步驟；不要求重裝已正確安裝的 A。

### 重複問題的架構診斷與決策

Green，主要建議是暫時沿用既有 typed composition seam，改善本機驗收入口說明，
信心高。能力是既有更新 discovery／admission；指定 acceptance URL 是一次驗收
例外。catalog 唯一 owner 為 app 的 `ManagedUpdateRuntimeConfiguration`；services
只消費 release source，UI 不判斷 channel 或直接讀 GitHub。helper 在 app 組裝邊界
傳入明確 URL，沒有第二份配置或隱藏持久設定，也未修改 production latest／keyring。

摩擦來源是對話／runbook 與實際啟動入口不一致；每次再發布測試 B，若繼續省略
helper 步驟，會重複產生最新版誤判、來源 probe 與重開程序的成本。
沿用入口說明是可逆的 docs 修改；在 About 顯示更新來源需要 typed presentation
與重新封裝驗證；新增持久 channel 則擴大產品／trust 契約，目前不選。

Safeguards：既有 helper 拒絕 production URL、驗證 Candidate 身分與 path containment，
同一 URL-only differential probe 可辨識這個問題；操作說明要求 ready marker 後
才點更新。完成條件是使用者的 helper ready、About B 成功、保留設定與原捷徑重開，
後三項仍 pending。未新增 production workaround 或做 refactor。

ADR：暫沿用可逆驗收入口，不改穩定來源。若測試版要成為長期使用者 channel，
應先定義 distribution/trust 與啟動來源的可見契約，再決定產品介面；不能以
本次測試例外默默擴張。下一個最高價值證據是使用者從一般 PowerShell 執行
helper 後的 ready marker／實際 About 結果。
