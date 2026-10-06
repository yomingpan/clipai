# ClipAI 正式版發行計畫

日期：2026-10-06（Asia/Taipei）。狀態：正式候選準備；尚未公開發布。

本輪使用者在下載並核對 r3 helper 後，以 `--timeout-seconds 600` 啟動，
回報「成功了。可以準備發行正式版 規劃一下」。記為本輪 About 更新
passed（使用者回報）；本次沒有另收集版本畫面、health receipt 或交易日誌。
設定保留、捷徑重開、reboot 仍待確認，不由更新成功推論。

## 發行範圍與基線

- 以已驗收的 r3 修正為功能基線，這輪凍結新功能，僅處理發行必要修正。
- 建議正式版本 **3.7.18**，正式 tag `v3.7.18`；執行前先查遠端版本／tags
  是否占用，再確定版本。這是提案，尚未改版本、建 tag 或建置。
- 本地 HEAD `43c3b7151b92e645eda21feaacb54ba8dc493872`，
  `pyproject.toml` 仍是 3.7.9；r3 B source 是
  `a890c2f4c7ba83d4fbc5703e0be50f158c9c0206`。需比對並固定正式來源，
  不能把目前 checkout 版本或歷史測試數直接當成正式候選證據。
- 交付 Windows 11 x64 的 `ClipAI` Setup、managed bundle、catalog、公鑰、
  hashes、notices、release notes、來源／建置／驗收證據。
- 沿用現有 builder、簽章 admission、更新及回復 owner；Setup 與 About
  使用同一 bundle。這輪不新增更新 channel 或另一套安裝引擎。

## 已通過與剩餘門檻

| 項目 | 現況 | 正式版仍需完成 |
| --- | --- | --- |
| r3 About 更新 | passed，使用者回報 | 正式身分與正式信任鏈的更新路徑 |
| r3 封裝、簽章 admission、資產驗證 | 歷史證據 passed | 正式候選固定來源與最終 hashes 重新驗證 |
| 正式 Setup／CI | builder 有正式模式；CI 仍用 technical mode | 正式 `ClipAI.Desktop` 身分、已審核 inputs、正式 signing |
| 正式 managed signer | 可配置；本輪未確認可用性 | 正式 Ed25519 authority、舊 key 相容性與輪替責任 |
| Windows publisher | pending | 最終 Setup Authenticode publisher／timestamp 與原生元件審核 |
| 設定保留、reboot、移除重裝 | 本輪 pending；有先前人工證據 | 正式最終檔案的完整循環 |
| 乾淨機 | 使用者先前 deferred | 準備工作照常進行；既有 release gate 仍未滿足 |
| 瀏覽器下載、新手首個結果、跨登入 gate | 未有本輪最終證據 | 最終簽署檔案與真實裝置／使用者觀察 |

現行 `verify_release_assets --require-release-ready` 會拒絕 technical candidate、
未完成的 admission、缺少 required gates 或錯誤的最終檔案簽章。
本計畫保留這個可執行 gate；若要調整發行政策，應另外明確決定並同步修改
契約與驗證，不能把 deferred 填為 passed。

## 執行順序

### 1. 固定來源與升級／轉移路徑

Agent 比對 HEAD、r3 A/B source、正式既有版本與 launcher/keyring；整理最小
正式 diff、release notes、版本與資產名稱。維護者確認 publisher／正式 signer
的可用來源，不讀出或輸出私鑰。

分開驗證三條入口：新使用者正式 Setup、既有正式安裝升級、Candidate 轉正式。
Candidate 與正式產品的 roots／身分／key 不同，不能承諾 Candidate 直接 About
升級為正式版；先規劃保留資料轉移並核對設定、API key 儲存與資料位置。
若需匯入，以明確選擇、typed use case 與既有儲存 owner 實作，不能手動搬動秘密。

r3 同時修正 app 與穩定 launcher；舊安裝只更新 app bundle 不會自動取得新 host。
正式既有使用者是否可直接 About 升級須用其實際 host／keyring 驗證；如不能，
提供經驗證的 Setup 維護／保留資料重裝路徑與發布說明，不先讓 latest 指向
已知無法安全更新的 bundle。

完成條件：三種使用者各有明確路徑；來源、版本、host 相容性與信任關係可審核。

### 2. 審核正式封裝 inputs 與簽署條件

Agent 整理 runtime、verifier、compiler、native files、依賴 notices 與固定 hashes。
目前 pinned OpenSSH `10.0.0.0p2-Preview` 的上游標示 non-production ready；
先評估可用的正式 verifier，再更新固定 inputs 並重跑驗證，不能只改 admission 字串。
來源：[上游 release](https://github.com/PowerShell/Win32-OpenSSH/releases/tag/10.0.0.0p2-Preview)。

維護者確認 Windows publisher、可用的 signer／timestamp、工具與元件散布條件；
Agent 整理選項與所需設定。正式 managed 內容簽章與 Windows publisher 簽章
分開驗證。Microsoft SignTool 支援簽署、timestamp 與驗證：
[Microsoft 文件](https://learn.microsoft.com/en-us/windows/win32/seccrypto/cryptography-tools)。
付費選型、取得憑證與帳號操作留到具體方案可審核後。

完成條件：已審核 inputs、正式公鑰設定、可用的 publisher signing 路徑。

### 3. 準備正式 CI 與候選

Agent 沿用 `.github/workflows/release.yml` 的唯一建置流程，保留隔離 validation
模式，為正式 tag 使用正式 Setup 模式。CI 保持候選上傳與公開發布分開。
補齊最終簽署後 provenance／hashes 重封存步驟，避免簽署後證據仍指向舊 bytes。

對固定正式來源跑 targeted、unit／architecture、Python 3.10–3.13 Windows CI、
language pack gate、完整 managed-bundle gate、installed-wheel smoke、compiled
Setup extraction 與資產驗證；對改動的相容性／簽署流程補必要測試。
生成一份 app wheel／lock／wheelhouse／managed bundle，再封裝正式 Setup。
簽署後重跑受影響的 extraction／hash／publisher 檢查。

完成條件：同一 source、版本、公鑰及 bundle；最終 Setup 的簽署與證據一致。

### 4. 驗收最終檔案

Agent 準備命令與證據表；維護者／測試者提供實機觀察。測試首次安裝、
離線啟動、首個 Action、退出及捷徑重開、reboot、About 更新、設定保留、
Windows 卸載與保留資料重裝。對已驗證舊版與新正式候選執行隔離更新，
必要時另建同 authority 的 A/B pair，保留更高 B 版本與獨立來源證據。

執行既有故障回復與跨登入矩陣；記錄下載中斷、準備失敗、啟動失敗回復、
操作衝突、時間及磁碟空間。由瀏覽器下載最終 signed hash，記錄 Windows
提示與新手首個結果。乾淨機 unavailable 時保持 deferred，其他準備照常完成。

完成條件：`docs/testing/installer-release-readiness-runbook.md` 的 required gates
有同一最終 Setup／bundle hashes 的證據，且 release-ready verifier 通過。

### 5. 審核並正式發布

Agent 先整理可審核的完整資產、release body、來源 tag、最終 hashes、驗收表、
升級／轉移說明與回復處置，再取得該次 tag push／正式公開發布授權。
正式 source tag 需在正式 builder 前固定；公開只在最終 gate 通過後進行。
不重標 acceptance Release，不覆寫已公開版本或更換其 bytes。

完成條件：正式 GitHub Release、不可變資產與預期 latest 身分一致。

### 6. 發布後驗證

匿名下載核對檔名、大小、整檔 SHA256 與真實簽章 admission；以受支援的正式
已安裝版本查正式 latest，完成一次明確 About 更新與重開。新使用者以正式
Setup 完成安裝。失敗時保留交易證據與可用舊版；暫停進一步推廣，維護者
決定公開處置，修正版使用新版本。不能把較低版本 catalog 當成已更新裝置的回復。

## 下一個可執行工作

先完成第 1 階段的 source／正式舊安裝／信任鏈盤點，同時整理第 2 階段的
signer 與 verifier 選項。之後才修改正式 CI、建置與安排最終檔案驗收。
時程由 signer／設備可用性與門檻完成情況決定，本輪不承諾發布日期。

參照：[release checklist](../RELEASE_CHECKLIST.md)、
[r3 evidence](../evidence/github-acceptance-publication-20261006-r3.md)、
[inputs admission](installer-release-inputs.md)。
