# 新對話啟動 prompt

以下整段可貼到新對話。先讓 AI 核對現況，再規劃與執行，不預設所有設備都已具備。

---

你是 ClipAI 的資深工程師兼 product owner。請接續已完成的本機 Preview，
規劃並執行下一階段「一致的安裝／更新發行流程」。不要只給建議或停在 plan，
完成目前環境允許的實作、測試、候選交付與驗收證據。

工作區：`C:\Users\88698\ClipAI_v2.worktrees\next_gen`。
交接基準 commit：`a0502d3`（請核對最新 HEAD，不要 reset 到此 commit）。
先讀 AGENTS.md，以及：

- `docs/Product_philosophy.md`
- `docs/ARCHITECTURE_BOUNDARIES.md`
- `docs/TESTING_STRATEGY.md`
- `docs/specs/installer-release-readiness-plan.md`（本次主要 plan）
- `docs/specs/first-install-installer-plan.md`
- `docs/contracts/first-install-contract.md`
- `docs/contracts/managed-update-contract.md`
- `docs/adr/0020-first-install-bootstrap-and-recovery.md`
- `docs/evidence/first-install-preview-r4-20261004.md`
- `.github/workflows/release.yml`、`docs/RELEASE_CHECKLIST.md`

背景：app version 是 3.7.8；r4 是本機 Preview build，包含 offline Python、
managed install／retained-data uninstall、ClipAI 圖示與桌面捷徑，以及 Gemini
刷新 credential 和完成頁修正。1,878 unit tests 曾通過，這不等於現在的 HEAD
或乾淨 VM 已通過。使用者確認新 Gemini key 可用，Save 後 Refresh 成功；
曾改用 Windows 卸載成功。不可重用先前 API key 的一次性網路驗證授權。

核心目標：同一 tag／commit 建立一次 app wheel、lock、wheelhouse、signed
managed bundle。Setup 封裝該 bundle；About 下載同一 bundle。使用者不用預裝
Python，可斷網安裝／啟動；雲端 AI 與更新仍需網路。開發與發行共用產品程式碼，
用實際產物測試控制差異，而不是宣稱兩種環境天然相同。

先做：

1. `git status --short`、核對基線，保留 `.tmp/` 及其他無關改動。
2. 唯讀盤點 clean VM、Windows image／授權、runner、簽署服務與權限。
3. 對照 plan 更新 P0–P4 的現況、依賴、驗收條件及阻礙；只有重大範圍變更才需
   另問，例行可逆實作直接進行。缺設備時繼續不依赖它的工作。

接著按 plan 執行：

- 收斂正式 builder：消費已產生且驗證的 bundle，不再各自重建 app 或解析 latest。
  Preview builder 的臨時信任 key 不得直接用於正式發行。
- 記錄 tag/commit／各元件版本與 hashes；測試 Setup 內含 bundle 与 catalog
  指向資產一致，安裝後實際 import 來自已安裝 wheel，不意外用 checkout。
- 保留 existing coordinator／installation gate／stager／materializer，不建立
  第二套安裝或更新引擎。碰到重複 ownership／繞路先做架構診斷，再最小修正。
- 在 clean snapshot 驗證 A 安裝 → About 更新 B → reboot → 卸載 → 保留資料重裝；
  B 必須是真正更高版本。涵蓋中斷、篡改、準備／啟動失敗、並行與安全回復。
  用隔離來源測試，不修改 production latest 或放寬簽章／keyring。
- 整合 GitHub Actions：現有 v* tag workflow 尚無 Setup，且 draft 後立即公開；
  加入正式候選 builder、artifact checks、簽署驗證與發布 gate，失敗不公開半套資產。
- 最終簽署檔再做瀏覽器下載／Windows trust／乾淨 VM 與少量新手第一個結果驗收。

授權與範圍：本次可修改 repo、執行合理測試及建立本機候選。不要擅自購買憑證、
啟用主機 hypervisor／改安全設定、傳送 credential、push tag 或公開正式 release。
遇到需要這些動作時，先完成其他工作並準備具體可審核結果，再提出必要問題。
不得刪除我的既有安裝／API key／資料來做測試；使用隔離的自有測試 scope。
不要為本任務新增多 channel、MSI、跨平台、遙測、通用 repair 或 runtime 自動更新。

交付要求：

- 持續更新主要 plan 與 evidence matrix，標註 passed/failed/pending/blocked。
- 每項證據附命令、候選版本/hash、環境與限制；unit／synthetic／本機／clean VM
  各自標示，不把空 PATH、fixture engine 或 CI runner 當全新使用者電腦證據。
- 修改 code 同步更新 contracts/tests，跑與風險相稱的 targeted、architecture、
  unit 與真實 smoke；不要無理由反覆跑已通過的測試。
- 最後提供檔案／候選連結、可重跑的驗收步驟、未通過 gates、需我處理的具體項目。
  沒有 signer／VM 就如實保留缺口，不宣稱「已可正式發布」。

請先簡短說明現況與執行順序，然後開始核對和執行。不要要求我重新提供已存在的
規劃，不要只回答「可以」或要求我再說一次「繼續」。
