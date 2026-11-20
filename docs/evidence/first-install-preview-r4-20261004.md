# Preview r4：移除完成頁與使用中提示

日期：2026-10-04。使用者以 r2 Setup 選 Remove，感覺流程像 Install，最後為 Finish。

## 裝置事實與限制

安全篩選 Setup log（只取 phase/result）發現當日 #001、#004 Remove
為 failed:RuntimeError；#002、#003 Install 為 failed:FileExistsError。
早期檢查有完整 Preview program root、owner phase=installed、兩個 private
Python 程序與 Start Menu shortcuts。使用者隨後改以 Windows 已安裝應用程式
卸載，後續程式目錄／Start Menu shortcuts／可見卸載註冊均消失。
保留資料目錄含 secrets/state/logs/managed-update，是 retained-data contract。

沒有刪除使用者資料、停止使用者程序或自動重新安裝。舊版 error 只有
RuntimeError，原移除的精確原因無法回溯；不能宣稱必定是 busy。
對原安裝的後續 readonly preflight 因 program root 已移除而不能執行。

## 已重現的完成頁 bug

官方 Inno source 在 ssPostInstall 後呼叫 ChangeFinishedLabel，覆寫自訂文字：
[Setup.MainForm.pas](https://github.com/jrsoftware/issrc/blob/main/Projects/Src/Setup.MainForm.pas)。
[event docs](https://jrsoftware.org/ishelp/topic_scriptevents.htm) 定義
CurPageChanged 為頁面顯示後 callback。

`setup_result_probe.py` 使用編譯後 Setup + 無副作用 fixture engine，只輸出
phase/exit，從 DeinitializeSetup 擷取真實完成頁 captions；不移除或安装 app。
修正前 failure exit=100、success exit=0，兩者內文均顯示
「Setup has finished installing ClipAI Preview on your computer.」，兩個 caption
checks 都 false。修正後 failure 為 Removal did not complete + Exit-from-Tray
指引；success 為 ClipAI Preview removed + retained-data 說明；兩個 checks true，
exit codes 保持 100／0。

Red：artifacts/first-install-diagnostic/setup-result-c57bb99917c2465689b588b0fbf10720/proof.json。
Green：artifacts/first-install-diagnostic/setup-result-fb14e99eb6b543488d2e5a05962c5ab1/proof.json。
Probe：`python -m experiments.first_install.setup_result_probe --script experiments/first_install/preview_setup.iss --stage <candidate-stage> --compiler <ISCC>`。

## Progressive architecture diagnosis／ADR

Yellow，推薦 local fix，信心高。Trigger：相似 completion feedback 第二次
影響驗收。保護 ownership-before-delete、single install gate、real settlement、
failed engine exit100，以及 user data retention。

1. Owner：services coordinator 擁有 install/uninstall terminal snapshot；
   platform 報告 typed busy；Inno adapter 擁有 wizard projection。
2. 能力：安裝／移除共用真實 terminal-result projection，不是 feature 特例。
3. Leakage：不能在 extraction-completed 時推論業務結果；Inno stock install
   lifecycle 与 application removal lifecycle 不相同。原 message 在錯誤 toolkit
   boundary 被覆寫，沒有新增 domain state owner。
4. Enforcement：一個 ShowOperationResult 在 wpFinished 與 ssDone 共用；native
   compiled regression 讀取最後 captions。InstallationBusyError 繼承 RuntimeError，
   既有 coordinator 只投影安全 class name，不傳任意原始 exception message。

Debt multiplier：繼續在 ssPostInstall 插入成功／失敗 label，第三種維護操作也會
再次遭覆寫。接受現況成本低但誤導；全換 installer 成本高；選 lifecycle seam
修正可直接回退。沒有第二套 uninstall 或跨層 process management。
先 red native probe → central projection + typed busy → unit/architecture →
green compiled probe → 新 candidate。Review trigger：下一個 maintenance intent
需要不同 terminal state、或原始 failure reason 再次無法定位。
最高價值未取得證據是實際互動 r4 ready/remove/failure page，以及原 RuntimeError
的精確原因；沒有把推論當成已解決的刪檔 bug。

## 驗證與交付

Native busy probe 啟動自己持有的 candidate Python child，real
assert_installation_idle 取得 InstallationBusyError，僅停止該測試 child。
Unit 驗證 busy 不刪 payload／owner、釋放 admission，service 提供可處理代碼。
Targeted + architecture 73 passed；完整 unit（含新增 busy 保護）1,878 passed、46 deselected。
r4 build：preview-383019e21d70403ba2261efb99cf427a。
Setup SHA-256：f7a181a8eda6523e49d5716f45007532701661e1bc0c17f3ad5a20ab074ec1c5。
本機 unsigned candidate，r3 icon/desktop/provider fixes 保留；公开 gates 不變。
