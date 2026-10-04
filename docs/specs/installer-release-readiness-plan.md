# Preview 後續：一致的安裝／更新發行流程

日期：2026-10-04。狀態：已執行 P0 盤點、P1 技術候選與 P3 CI 改造；公開發行 NO-GO。基準 commit：`a0502d3`。
本文件接續 `first-install-installer-plan.md` 的 D／E 與尚未完成的 A gates，
不重做已完成的本機 Preview。啟動提示詞見 [執行 prompt](installer-release-readiness-prompt.md)。

## 目標與完成定義

同一 tag 對應同一 source commit、app wheel、hashed lock、signed managed bundle。
Setup 內含該 bundle；About 取得同一 bundle。兩條路最後得到相同 app 內容與
版本，差異只在首次安裝需要 bootstrap／Windows integration。

最終交付是可供審核的正式候選及 evidence，不以「CI 綠燈」代替新電腦驗收，
也不預設已取得公開發布或付費簽署的授權。

- Windows 11 x64 一般使用者，不預装 Python／Git／OpenSSH，可斷網安裝與啟動。
- Gemini 等雲端功能、模型刷新、線上更新需要網路；離線能力不包含雲端推論。
- 離開 Setup、清除測試暫存、重開機後，啟動、更新及維護仍可用。
- 安裝 A → About 更新 B → 失敗回復 → 卸載 → 保留資料重裝皆有真實證據。
- CI 建置／驗證／候選發布由固定輸入驅動；正式 Setup 簽章與依賴散布條件確認。
- 最終檔案的下載／Windows 提示與少量新手首次結果有紀錄。

## 執行前基線與不可誤判的地方

目前 app 為 3.7.8，r4 是本機候選識別；r1–r4 不是 About 可比較的升級版本。
1,878 unit tests 已通過；r4 compiled Setup 的成功／失敗完成頁及 busy detection
有證據。實際 r4 互動驗收、乾淨 VM、正式簽章與官方更新循環仍未完成。

現有 `.github/workflows/release.yml` 由推送 `v*` tag 觸發，檢查 tag 與
`pyproject.toml` 版本一致，產出 signed managed ZIP/catalog/keyring；沒有 Setup。
目前建立 draft 後立即公開發布，必須先處理發布 gate，不能直接推 tag 做探索。
`experiments/first_install/build_preview.py` 會重建 wheel 並產生本機信任 key，
只能作 Preview 工具，不能直接變成正式 CI signing／artifact ownership。

About 預設讀正式 GitHub latest catalog。本機 Preview 的私有候選 key 與正式
keyring 不同，不承諾 Preview 可直接升級成正式版。正式切換先定義保留資料
卸載／重裝方式，不新增多 channel 更新引擎。

## 2026-10-04 執行狀態

最新續作：Tray／完整移除已提交 `01bfb04`，使用者回報新版人工測試正常。
使用者要求接續四步後，明確表示沒有 VM／第二台電腦，先跳過乾淨機驗收；
此 gate 記為 deferred，不是 passed。已建立真實較高版本 3.7.9（`7bcccb1`），
加入 `release-validation/**` 隔離分支以執行同一 CI builder，已觸發遠端候選與
Windows CI。首輪找到舊 tag-expression 測試未同步，修正後需重跑確認。
正準備共用一次性信任金鑰的 3.7.8／3.7.9 Setup＋bundle 配對；正式 signer、
實際 About 點擊更新與最終簽署檔／新手觀察仍須各自取得真實證據。

後續進度：首輪變更已依使用者要求提交為 `64b61c9`。使用者回報舊 Candidate
七步人工安裝／啟動／重開機／卸載／保留資料重裝均正常，另指出第一次 provider
設定完成後 Tray 仍黃。已修正 readiness projection，並依追加需求提供明確
選擇的完整移除（含設定、API key、資料）及 maintenance helper 清理。
本輪實作與 1,930 unit／native helper／compiled wizard 證據見
[後續驗收](../evidence/tray-readiness-full-removal-20261004.md)。新候選仍為本機
3.7.8，需人工驗證新增選項；未宣稱是 About B 或乾淨 VM／正式簽章通過。
以下基線與首輪 matrix 保留為歷史執行紀錄。

HEAD 仍為 `a0502d34cfa2b1ab554c480d39b8b8813d1ef201`，未 reset、commit、push
或發布。開始時只有本 plan 與 prompt 未追蹤；使用者既有 `.tmp/`、安裝、key
及資料均保留。實作為目前 working-tree diff；不是另一個已驗證 tag。

| 階段 | 狀態 | 已完成／驗收 | 依賴與未通過 gate |
| --- | --- | --- | --- |
| P0 | passed 盤點；pending admission | 基線、必讀契約、readonly host/tool inventory、ownership 診斷與固定 inputs | WMI 拒絕；無確認的 VM/image/license/CI 權限/signer；r4 真人與正式 native/license admission 尚缺 |
| P1 | passed 技術候選；pending 正式身份 | 固定 bundle/catalog/keyring → Setup；bootstrap 取自同 wheel；完整 Git source 比對；compiled extraction hash；no-index installed imports；provenance、notices；substitution tests | 本機 r4 authority、未驗證 tag、unsigned Setup；正式 tag/keyring/signing 尚缺 |
| P2 | passed local cycle；blocked clean VM | 編譯 EXE 安裝/duplicate/busy/broken-venv remove/retained-data reinstall/final remove；existing fault/loopback gates；attended About source launcher/runbook | Desktop 因使用者 app 活動跳過；無 VM/reboot/實際 A→B/About/cross-logon/峰值空間/首個 Action；B 必須較新，未把 r4 重建當 B |
| P3 | passed source/tests；pending remote CI；blocked official trust | tag workflow 共用 builder，保留 managed gate、packaged/extraction/asset gate，contents read、僅 artifact upload；無自動公開；exact-hash publisher gate | workflow 未 push/執行；technical mode 不能公開；簽署與合法 input admission 待供應 |
| P4 | blocked | go/no-go、final-hash acceptance envelope 與公開步驟可審核 | 沒有最終簽署候選／clean VM／瀏覽器 trust／新手首個結果證據；沒有公開授權 |

交付：`artifacts/installer-release-readiness/delivery-20261004/output/`。
App 3.7.8；Setup `0f3789af3c44842c0759d2bdd8f2434c2ea68d88e29924471148befbe5cb6e3c`；
同一 managed bundle `5a01500508eb35575d72351d1d5c7618383197964f8b4b564ba97be1c27b2223`。
Setup 內解出的 bundle、交付 ZIP 與 catalog identity 均一致；尚未把該 URL 實際
公開下載或 About B 成功記成 passed。Candidate 與 Preview/正式 roots 分離。

完整 [evidence matrix](../evidence/installer-release-readiness-20261004.md)、
[ownership diagnosis](../evidence/installer-release-ownership-20261004.md)、
[inputs/admission](installer-release-inputs.md)、
[可重跑 runbook](../testing/installer-release-readiness-runbook.md)
列出命令、環境、限制、未通過 gates 與下一步。缺設備不阻止以上本機工作；
公開發行仍 NO-GO。沒有購買、啟用 hypervisor、改安全設定或傳送 credential。

## P0：核對基線與執行條件

1. 讀 AGENTS、產品哲學、架構與測試文件，以及首次安裝／managed-update contracts。
2. 核對 HEAD、工作區與 release checklist，更新過時描述，區分現在事實與舊證據。
3. 補 r4 的互動驗收：圖示、桌面、首個 Action、重開、使用中拒絕移除、成功
   移除、保留設定重裝。缺使用者操作時明列 pending，不宣稱整輪通過。
4. 唯讀盤點可用 VM／hypervisor、Windows image／授權、一般使用者帳號、CI
   權限與簽署服務可行性。未獲授權不安裝 hypervisor、改主機安全設定或購買憑證。
5. 定義 Windows／Python ABI、runtime/verifier/compiler/wheel 來源、版本、hash、
   notices、可散布條件與維護責任。查官方來源，不把現有 Preview 工具當正式選型。

產物：baseline／能力盤點、release-inputs、缺口與責任表。
Gate：關鍵能力缺失有具體處理路徑；無 VM 時可先執行 P1／P3，P2 保持 blocked。

## P1：同一產物、兩個入口

1. 在改動前診斷 build／installation／publication ownership，沿用唯一驗證、
   stager、materializer、installation gate。必要時做局部共用，不新增 installer engine。
2. 正式 Setup builder 接收已驗證的 bundle、publication metadata、bootstrap
   inputs／keyring；不得再解析最新依賴、重建 app wheel 或生成臨時正式信任 key。
3. 單次 build 建立 release wheel、lock、wheelhouse、bundle，再產生 Setup。
   約束 Setup 內含 bundle bytes/hash 與 catalog 指向下載檔一致。
4. 建立去敏 provenance：tag、commit SHA、app/launcher/runtime/verifier/compiler
   identity、lock/wheel/bundle/Setup hashes。版本各自有責任，不能混為 app version。
5. 開發保留 editable 工作流；新增使用同一 release lock/wheel 的驗證環境。
   驗證安裝後實際載入 package 的位置，避免從 checkout／PYTHONPATH 意外 import。
6. 將 code bug、dependency resolution、artifact build、install/startup、update
   failure 分開記錄，仍使用既有安全 diagnostics，不新增遙測平台。

產物：正式 builder seam、產物一致性檢查、packaged-app smoke、provenance。
Gate：替換 bundle／版本／keyring 時安全拒絕；Setup 與 About 的 app payload
一致可用 hash 證明。路徑差異不能直接以整個 venv byte hash 判斷不一致。

## P2：乾淨 VM 與可重複更新循環

1. 建立可恢復的 clean snapshot；記錄 Windows build、權限、CPU 與 prerequisites。
   VM 內沒有開發工具，與網路隔離；空 PATH 不是乾淨 VM／真正斷網的替代證據。
2. 安裝固定候選 A；斷網啟動、退出 Setup、清除該測試自有暫存、重開機，再啟動。
   恢復網路後，以明確 user intent 驗證 provider 與首個 Action。
3. 建立可比較的新候選 B（實際更高版本）；以既有 catalog/source injection seam
   在隔離測試發行來源完成 About 更新。不修改正式 latest，不放寬正式信任驗證。
4. 每輪从 snapshot 重建 A → B → 重開 → 卸載 → 保留資料重裝。
   比對版本、payload identity、launcher health、native integration 及設定保留。
5. 必測失敗：下載中斷、hash／manifest／簽章篡改、準備失敗、更新後啟動失敗、
   使用中／同 gate 操作衝突。失敗保留可用版本或給出可執行恢復出口。
6. 補真實並行／跨 logon gate 與中文／空格路徑證據；其他 cases 依風險用
   deterministic tests 覆蓋。設定有限輪數、timeout 與清理範圍，不做無限 soak。
7. 量測 Setup 大小、峰值／完成磁碟空間、階段耗時；記錄數據後決定門檻，
   不以下載大小推估安裝空間，不因尚未量測而先重寫封裝。

產物：可重跑 harness／runbook、正常及故障 evidence matrix。
Gate：正常完整循環在 reset 與 reboot 後可重現；每個必要故障有安全終態，
資料比對排除或明列預期 app writes。Synthetic／local HTTP／VM 證據分別標記。

## P3：CI、正式信任與候選交付

1. CI 沿用 P1 的 builder，保留現有 managed update gate，加入 packaged smoke、
   Setup identity／integration 檢查；不能只有 editable source tests。
2. tag 必須符合 app version 且指向已驗證 commit；同一正式版本不覆寫不同內容。
   本機候選用獨立 build ID，正式版用可比較的新版本；preview/prerelease 如需
   引入，先確認現有 version parser／latest 行為，不擴成多 channel 系統。
3. 明確區分 managed Ed25519 內容信任與 Windows Authenticode publisher 簽章。
   signing secrets 不寫入 repo/log/bundle；簽署後驗證 timestamp／publisher/hash。
   無合法 signer 時交付 unsigned 技術候選，正式 gate 保持未通過。
4. 改掉 draft 後立即公開的流程：build/verify 產生候選或 draft；公開步驟在
   必要 gates 與授權滿足後才執行。不要擅自改 branch protections／付費服務。
5. 維持 Setup（新用戶）、ZIP/catalog（About）、keyring、notices、provenance
   的完整資產集合；檢查缺 asset、錯 URL、錯版本時不發布半套 release。
6. Draft 資產不可作一般使用者 About latest 測試來源；測試可用隔離來源，
   正式發布後再驗證下載來源可讀且身份匹配，不提前把正式指標改到候選。

產物：workflow、release checklist、候選 assets、簽署驗證與發布 gate。
Gate：任一步失敗不公開；Setup 內含的 bundle 與 About bundle 是同一產物。

## P4：最終交付驗收

1. 使用最終簽署候選（精確 hash）從瀏覽器下載，記錄 Windows 提示及結果。
   簽章不保證沒有 SmartScreen 提示，不關閉防護來通過驗收。
2. 找少量未使用過 ClipAI 的人觀察下載、安裝、key 設定與第一個結果。
   記錄協助次數與阻塞點，不把少量觀察宣稱成有代表性的流失率。
3. 同一候選重跑受簽署／封裝改變影響的 VM gates，留下 release go/no-go 表。
4. 公開發布需另有直接授權；未授權時交付完整可審核候選與確切發布步驟。

## 優先序、ROI 與執行方式

P0 先發現環境／簽署阻礙；P1 消除兩套 build 漂移；P2 證明新電腦與回復可靠；
P3 讓後續版本重複同樣流程；P4 驗證使用者能成功開始使用。
正式發布需要全部必要 gates；簽署可行性早查，但 final trust test 在簽署後執行。

此階段不做 ARM64／macOS、MSI／企業部署、多 channel、自動 runtime 更新、
完整 repair、重写 launcher、大型 onboarding 或遙測平台。
缺 VM／憑證不阻止獨立的 builder、tests、CI 與 runbook 工作，不能假填驗收。

每項 evidence 記錄 passed/failed/pending/blocked、執行命令、候選 identity、
環境、結果、限制與下一步。修 bug 更新 contract/tests；依風險執行 targeted、
architecture、unit 與真實 smoke。每個階段以小而完整的 diff 交付，不擅自 push
tag、發正式 release 或承諾 Preview 無縫變成正式版。
