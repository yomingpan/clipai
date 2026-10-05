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
