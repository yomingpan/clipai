# Exit 後卸載失敗：診斷與修正

## 1. 判斷

Yellow；本輪建議局部修正 maintenance terminal projection。
忙碌檢查與錯誤回報缺口有直接證據；殘留 launcher 的阻塞位置尚未確認。

## 2. 證據與推論

使用者截圖為 supervisor 的通用 removal/helper-cleanup error。唯讀 inventory
確認 Exit 後版本 Python 已消失，但 21:49 的 launcher redirector/runtime
仍在；實際 `assert_installation_idle` 拋出 `InstallationBusyError`。
該啟動的 launch receipt 在 21:49:39，health 在 21:50:44，超過 20 秒。
這證明 health 晚到；不能據此聲稱已取得殘留 launcher 的 stack 或確認對話框。

native supervisor 回歸測試使用真實子行程、等待與清理，只替換 attended
MessageBox；worker busy、helper 成功清除時仍顯示截圖原文。修正前測試為紅。
normal-launch timeout/invalid-health 測試也證明失敗後未呼叫 owned lifecycle stop。

## 3. 保護行為

保留 owned installation admission、執行中拒絕卸載、保留資料預設、完整移除的
明確 intent、同一 Setup retry，以及僅清理本次 helper 的路徑與 reparse 防護。
本次診斷不終止使用者現有程序、不卸載其安裝、不讀設定或 credential。

## 4. 四項診斷

- owner：`UninstallCoordinator` 擁有卸載結果；supervisor 只擁有本次 helper
  process settlement/cleanup。`ManagedCurrentLaunchCoordinator` 決定 normal
  startup failure；既有 `ManagedApplicationLifecycle` 擁有 launched receipt/process。
  這條邊界的問題另外保留為待驗證事項，不新增 process owner。
- capability：跨 process terminal feedback 與 failed-launch settlement 是共用能力，
  不是跳過 idle gate 的例外。
- propagation：quiet worker 丟失 typed error；normal launch 的失敗邊沒有 settlement。
- enforcement：native busy/cleanup/invalid-result tests 與 quiet worker projection tests。

## 5. 債務倍率

隱藏 terminal state 與漏掉失敗 settlement。若未修正，repair、再啟動與 runtime
更新會各自添加「猜 exit code／忽略 Python PID」的特例，侵蝕 ownership proof。

## 6. 選項

保留現況成本低，但持續無法診斷；跳過或掃描終止 Python 有錯刪風險；局部修正
保留既有 owner，改動小且可回退；全面重寫 installer 成本高、缺乏證據支持。

## 7. 建議

本輪只補 helper-scoped、有限欄位的既有 terminal snapshot projection。
worker removal 與 supervisor cleanup 分開呈現；
任何 missing/malformed/contradictory result 不得顯示成功。不保存 stdout、traceback、
credential 或 user content。不得加入第二個 uninstall coordinator 或 process registry。

## 8. 順序

先紅測試，再小範圍修正，再 targeted/unit/architecture/native smoke。
未保留試作的 normal-launch `stop` 修正：目前 Windows venv redirector 與
base runtime 是兩個程序，現有單一 Popen stop 沒有完整父子程序 settlement
證據。不能把該 unit seam 通過當成修好此次 launcher 殘留。
既有公開 acceptance assets 保持可追溯；修正必須重新建置後才存在於 Setup。
使用者現有安裝的恢復及 attended uninstall 證據見下方；launcher 殘留的長期修正仍待驗證。

## 9. ADR 摘要

沿用 ADR-0020 的單一卸載 owner、明確 scope 與 fail-closed。選擇安全 terminal projection，排除 raw log
capture、忽略執行中程序、任意清除 temp，以及全面 installer 重寫。
review trigger：第二個 terminal owner、無法 settlement 的 child 或新的維護入口。

## 10. 未確定事項

殘留 launcher 的 stack／隱藏 modal window、首次啟動耗時原因仍未確認。
舊 launcher 結束後的 idle gate 與使用者卸載重試已通過，見下方；
不得把這次恢復成功當成已修正 launcher 殘留成因。

## 測試證據

- 紅測試：`tests/platform/test_maintenance_helper.py -m integration -q` 原始 busy
  case 得到截圖完全相同的通用訊息，即使 helper 已清掉；1 failed、2 passed。
- 修正後原生 supervisor：15 passed、3 deselected、20.38 s。涵蓋 busy、其他
  exception、成功、exit/phase 矛盾、缺 result、invalid JSON、超長 result、錯誤
  欄位型別，以及 worker 成功或 busy 但 helper 檔案仍被占用；只替換 attended UI。
- 架構：`tests/architecture -q`，56 passed、5.62 s。
- quiet bootstrap terminal projection 與 bounded writer 已納入 unit suite。
- 完整 unit：`.venv/Scripts/python.exe scripts/run_unit_tests.py -- -q`，
  1,953 passed、61 deselected、52.91 s；`git diff --check` 通過。
- 已發布的 acceptance-20261004 資產沒有變更；本輪 source fix 不會自動進入已下載 Setup。

## 使用者授權的現有安裝恢復（2026-10-05）

使用者明確同意只停止先前確認的 PID 5140、24420。停止前重新核對各自的完整
executable path、parent PID、精確 creation time，並保留 process handle，避免 PID
重用。結束 runtime PID 24420 後，launcher redirector PID 5140 自行退出；再次
確認兩個 PID 都已消失。實際 `assert_installation_idle` 現在輸出
`INSTALLATION_IDLE`、exit 0；安裝根與 shared data 根仍存在。
自動工具沒有執行卸載、刪除檔案、讀取或改寫設定／API key。使用者隨後回報
「成功卸載了」。唯讀確認 `%LOCALAPPDATA%/Programs/ClipAI Candidate` 已不存在，
`%LOCALAPPDATA%/ClipAI Candidate` 仍存在，與保留 shared data 的卸載相符。
本次開發電腦 attended uninstall retry 記為 passed；未驗證 shared data 內容、
完整移除、乾淨 VM 或 launcher 殘留的長期修正。
