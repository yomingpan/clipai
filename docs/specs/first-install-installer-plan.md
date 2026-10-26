# 首次使用者 Installer 規劃

狀態：依使用者「繼續完成直到可以驗收」指示，已實作共用首次安裝協調、Windows integration 與隔離的 ClipAI Preview Setup，進入本機候選驗收。A1 簽署／完整來源 admission、A2 乾淨 VM、A3 真人觀察保留為公開發行 gate，尚未通過。日期：2026-09-30；執行更新：2026-10-01。

## 1. 判斷與建議

架構診斷：Yellow。建議採增量遷移，以可信 Setup 封裝既有 managed install 能力，保留現有 source 啟動供開發使用。信心：責任邊界高，runtime 封裝可行性待實機確認。

主要問題是首次安裝的 bootstrap 與初始信任尚無完整產品入口；不是缺少版本切換引擎。避免在 BAT、Setup script 或 UI 再建立一套安裝／更新規則。

產品完成條件包含「新使用者取得第一個有效結果」，不能只以 Setup 結束或 runtime health 作為首次使用成功的證據。進入正式 B／C 實作前，先完成 A 階段的契約、乾淨 VM 技術可行性與新手流程確認；完整產品旅程在 C／E 驗收。

本次 review 的投資原則：優先避免整批新電腦無法啟動、安裝後無法開始使用，以及失敗後無法脫困。先量測封裝成本，不為尚未證實的企業部署、跨架構或自動修復需求增加機制。ROI 為影響、成本與支援負擔的定性判斷，目前沒有安裝量或流失數據。

## 2. 證據與應保護的行為

- `.github/workflows/release.yml` 已產生 wheel、sdist、signed managed ZIP、catalog 與公開 keyring，尚未產生 Setup。
- `docs/RELEASE_CHECKLIST.md` 明確記載不建立 executable installer。
- `ClipAI/platform/managed_installer.py` 已共用 `VerifiedManagedBundleStager` 與 `PreparedManagedPayloadMaterializer`，建立版本與 launcher 後才發布安裝 marker；拒絕既有目標與 install/shared roots 重疊。
- `main.py` 的 `install` 路徑需要可執行的 Python 安裝工具、app-root keyring 與 `ssh-keygen`；下載 ZIP 本身不能解決 bootstrap。
- `candidate_environment.py` 依賴完整 Python 的 venv、ensurepip、pip；不能未經驗證直接換成 embeddable runtime。
- `tests/platform/test_managed_installer.py` 已覆蓋成功、失敗清理與 launcher 建置失敗；現有完整 managed-update gate 應繼續保留。
- 現有失敗清理可能保留殘餘檔案，重試會拒絕覆蓋；首次安裝中斷後的 ownership 與恢復契約仍需設計，不應假設已有透明重試。
- `main.py` 的 manifest verifier 仍透過 `PATH` 尋找 `ssh-keygen`；Setup 當下提供工具不代表離開 Setup、清除暫存或重開機後仍可啟動與更新。
- `ClipAI/app/runtime.py` 的 readiness callback 在 runtime start 成功後、進入 UI event loop 前執行；它不證明 provider 已設定，也不證明使用者取得結果。現有 `docs/PROVIDER_SETTINGS.md` 描述 Tray 設定入口，不能當成首次使用導引已完成的證據。
- 現有 installer 分別 materialize version 與 launcher 環境，並保留 transaction bundle／staging；下載大小不能直接當成安裝峰值空間，交易暫存的清理責任與時機需明定。

以上是規劃開始時的程式碼事實。選擇自帶 runtime、完整 Setup 與下列 UI 是本提案，不代表目前已存在。A 階段新證據與尚缺 gate 見第 10 節，實驗工具不改變現有 production 行為。

## 3. V1 使用者流程與範圍

預設規劃 Windows x64、每使用者安裝、不要求系統 Python／Git／WinGet、不修改全機 PATH、不預設開機自啟。Windows 最低版本需由乾淨 VM 與所有依賴驗證後鎖定。

1. 官方下載說明以 `ClipAI-Setup-{version}-windows-x64.exe` 作為新使用者唯一主要入口；wheel、managed ZIP 與 catalog 保留為開發／更新資產，不要求新手自行判斷。
2. 開啟即顯示版本、安裝位置、經量測支持的所需空間與「安裝」按鈕；必要 prerequisite、可能的權限或重開機需求在副作用前說明。
3. 明確按下安裝後立即顯示真實階段：檢查、驗證、準備環境、安裝、檢查。
4. 成功後顯示「已安裝」，提供「啟動 ClipAI」；啟動成功須等待既有 health 證據。
5. 首次啟動提供可見且可返回的設定入口，重用既有 Provider Settings 契約；沒有 provider credential 不應被混淆為套件安裝失敗。說明使用自己的 provider／API key、可能產生的 provider 費用，以及最短的 Action 操作範例。V1 不建立完整教學系統。
6. 使用者完成或略過設定後仍能找到 Tray／設定入口。由使用者明確觸發一次 Action，驗證取得有效結果、可關閉結果並可再次使用；略過設定不顯示「已可使用 AI」。安裝、啟動 health 與首次有效結果是分開的完成條件。
7. 後續 app 更新沿用 About → existing managed update handoff；超出 runtime／launcher 相容範圍時使用第 6 節的維護出口。

V1 不包含 source 自動遷移、任意資料夾覆蓋、全機安裝、完整 repair、降級與新的背景更新排程。相容的完整安裝引導使用既有更新入口；部分安裝依明確恢復契約處理。自身殘餘清理、OS integration 補償與保留資料重裝屬於最小恢復範圍，不延伸為通用自動修復。

首次啟動、呈現設定頁或 health 檢查不產生 provider invocation。任何 credential 驗證或可能計費的請求，沿用既有明確 typed intent 與提示；Installer 不取得或代管 API key。

建議預設 install root 為 `%LOCALAPPDATA%\Programs\ClipAI`，shared root 為 `%LOCALAPPDATA%\ClipAI`；必須與現有 ApplicationPaths 策略核對後定案，兩者不可巢狀或重疊。

## 4. 四項架構診斷

| 問題 | 決策 |
| --- | --- |
| 單一 owner | 現有 filesystem installer 擁有 managed 安裝落盤與 marker 發布；services 指定唯一首次安裝 coordinator，擁有 admission、lifecycle、取消與恢復決策；app 擁有 composition 與 dispatch；Windows integration adapter 執行捷徑、卸載註冊與精確 OS 操作；Setup 僅為發行封裝及 UI adapter。不得在 Setup 另存一份版本或恢復政策。 |
| 能力或特例 | 首次安裝是可重用的部署能力，未來 silent install 與離線部署可沿用；不是 About 特例。 |
| 邊界洩漏 | Setup 若自行解析 manifest、執行 pip、寫 pointer／marker、管理 rollback，會複製既有 platform／services 的知識。UI 不得取得這些實作權限。 |
| 強制 safeguard | typed intent／snapshot、operation-scoped cleanup、shared stager/materializer、同一 installation gate、architecture tests，並由乾淨 VM gate 驗證安裝→離開 Setup→重開機→啟動→更新→卸載／重裝。首次使用另有明確觸發的 Action 驗收。 |

主要 debt multiplier 是 duplicated ownership 與 bootstrap dependency ambiguity。若往後加入 silent install、repair、channel selection，將三次擴大 script 的分支與狀態歧義；應讓入口共用 policy，而不是各自修改檔案。

## 5. 初始信任與 manifest

- Setup 必須自帶可信的 bootstrap engine、公鑰與該次發行的固定 metadata；不可先執行尚未驗證的 ZIP 內程式來驗證自己。
- managed manifest 與簽章沿用既有 schema，不增加第二套內容 manifest。
- Setup 固定攜帶同一 tag 的 ZIP 與 catalog identity；V1 不在安裝當下追逐 latest，避免同一 Setup 安裝出不同版本。
- Windows Authenticode 驗證 Setup 發行者；Ed25519 驗證 managed payload，兩者責任不同。正式外部發行需決定簽章憑證、CI secret 與 timestamp 配置。
- 簽章不保證消除 SmartScreen 提示；新檔案或 publisher reputation 不足仍可能被警告，EV 憑證也不保證繞過。A 階段確認簽署身份取得資格、可用的 CI 簽署方式與 timestamp；不只為期待消除提示而購買較昂貴憑證。
- 以瀏覽器下載最終簽署的候選 Setup，在乾淨 Windows 實測 publisher、SmartScreen／Smart App Control 提示與執行結果，與本機複製檔案的結果分開記錄。官方下載說明提供辨識來源與 publisher 的方式，不要求使用者關閉安全防護；阻擋或未覆蓋狀態不得標示為通過。
- bootstrap runtime、驗證工具與其必要依賴也必須納入可信 Setup 封裝及固定 hash／來源／license 清單。
- downloaded keyring 不能自行擴大信任；更新包不能改寫 stable launcher keyring。
- 私鑰不進入 Setup／ZIP／workflow artifact。

## 6. Runtime 與封裝選型

主方案：完整離線 Setup，自帶 compatible runtime 與可信安裝工具，再重用既有 install seam。下載較大，但可避免首次安裝依賴多個外部下載與系統工具。

候選 Setup 外殼為 Inno Setup，採 per-user non-admin mode；僅處理封裝、畫面、捷徑及卸載入口，不寫 managed 安裝政策。封裝工具正式採用前需做一個乾淨 VM 技術 gate。

第一階段必須回答：

- 何種固定 Python 3.12 runtime 可攜帶並支援現有 venv／ensurepip？禁止把既有 venv 搬目錄當成可攜環境。
- bootstrap 如何在執行任何 downloaded payload 前取得可信 engine 與完整依賴？可封裝 bootstrap executable，但不得順勢重寫整個 app 為 frozen distribution。
- verifier 使用 self-contained OpenSSH 工具或新的 crypto adapter？需維持現有 signature namespace／format，並驗證 license、依賴與清理。安裝後由 composition 注入可信固定位置，不依賴使用者系統 PATH 或 Setup 的暫時 PATH。
- Python base runtime 安置在 install root 的固定工具目錄，必須在所有版本 venv 的生命週期內保留；stable launcher 不應因更新切換而失去 base runtime。Runtime、verifier、keyring 與可信維護入口不得依賴 Setup 暫存位置。
- pywebview／WebView2、pythonnet／.NET、VC runtime 與媒體依賴在乾淨 Windows 的最低條件為何？僅安裝有證據需要的 prerequisite，取得明確使用者意圖與真實失敗回報。
- launcher／bootstrap／app 各自版本與相容條件如何紀錄？沿用現有 launcher_version，避免混用 app version 或新增重複身份。

Python 官方說明指出 embeddable distribution 不支援一般 pip 管理方式；因此本提案不把它視為現有 installer 的直接替代品。

其他方案：online bootstrap 下載小但增加 transport／proxy／runtime 來源工作；source BAT 成本低但不提供 managed eligibility；全 app 改為 frozen distribution 改動範圍大。本期不選這三者。完整 Setup 可回退到獨立 release asset，不影響現有更新 schema。

### 6.1 自足性與 prerequisite 契約

「完整離線」指指定支援環境中的安裝與 runtime 啟動不需要網路下載；provider 設定驗證與 AI Action 可另需網路，不混入離線安裝 gate。若必需 prerequisite 無法同時滿足離線與 per-user non-admin，A 階段必須修訂並明示產品承諾，不能靜默改成線上下載或要求提權。

A 階段交付 prerequisite 表，每項記錄用途、文字核心或選用能力、最低版本／架構、偵測方式、可信來源／hash／license、是否隨包攜帶、所需權限、重開機條件與失敗結果。WebView2 的線上 Bootstrapper 與離線 Standalone Installer 不可混用為同一離線證據。

對只影響語音等選用能力的依賴，先驗證可否保留文字核心並投影明確 capability unavailable。無法隔離時要列為必要依賴及其原因，不以 UI 隱藏掩蓋啟動失敗；是否可降級尚未驗證。使用共用 prerequisite 時不得在卸載 ClipAI 時移除它。

乾淨 VM 必須沒有系統 Python、Git、OpenSSH；安裝與啟動階段斷網。安裝後關閉 Setup、清除本操作的安裝暫存並重開機，再由 stable launcher 捷徑啟動。恢復網路後從該安裝執行一次 About 更新，證明 verifier／base runtime 的持續可用性。

### 6.2 Runtime／launcher 維護出口

正式 V1 前必須指定 bootstrap runtime、launcher、verifier 與 trusted keyring 的維護責任，記錄實際發行版本、來源與相容範圍。App 更新沿用既有 manifest／catalog 的相容條件，並驗證 native wheels 與固定 runtime 的相容性；不得把 app version 當成 runtime 或 launcher version。

V1 不新增完整 runtime 自動更新引擎。最小維護出口為「可信卸載／清理入口保留 shared 資料 → 使用相容的新 Setup 重裝」，需要真實驗收，且卸載／清理不能只依賴損壞的 app 或 version venv。相容性檢查失敗時提供這條具體路徑，不能讓 About 要求新 Setup、新 Setup 又要求 About。資料不相容時需明確停止並保留資料，不自動重設或宣稱無損重裝。

不原地覆寫仍被 current／previous version venv 使用的 base runtime，不讓 runtime 維護破壞回滾能力。首次維護發行前重做 ownership／相容性診斷；自動化需求有證據後再擴充。A 階段須定案並驗證最小重裝路徑，不能只把安全修補留為未來 review trigger。

## 7. 安裝狀態、取消與卸載

首次安裝 lifecycle 的 snapshot 必須區分檢查、驗證、準備、提交、已安裝、失敗與取消。安裝完成與 app 啟動完成分開呈現。

先解決既有 installer 的以下落盤契約，再提供 UI 重試：

- 安裝 mutex 下重新檢查目標，拒絕其他 transaction 的目錄；不能只依賴取得 mutex 前的檢查。
- 在 side effect 前保存 installation operation ownership；中斷／取消只清理由同一操作建立的檔案。
- marker 發布前取消可安全清理；發布後不把取消偽裝為未安裝，按第 7.1 節投影 payload 已提交、integration 是否完成及未啟動的真實狀態。
- 不刪除已存在或不明 ownership 的目錄；殘餘失敗要明確顯示，不無限重試。
- 快捷方式只指向 stable launcher，不指向特定版本。
- shortcut／OS uninstall registration 由同一 Windows integration adapter 管理，與 managed marker 的完成／補償順序需定義；不要讓 Setup 與 app 各建立一份無關安裝清單。
- 卸載停止精確的本安裝程序、移除本安裝的 runtime／版本／捷徑。預設保留 shared 使用者資料；刪除資料需另外明確選擇，不遞迴刪除整個 shared root。

### 7.1 恢復與完成狀態

Managed marker 發布是 managed payload 提交點，不等於完整 Setup 成功。完整「已安裝」需 payload、stable launcher 與必要卸載入口已就緒；OS integration 未完成時投影「套件已安裝，整合未完成」及具體恢復操作。發布後不可假裝取消已移除安裝，或為補償而刪除已提交版本。

| 檢查結果 | 允許的處理 | 使用者看到的結果 |
| --- | --- | --- |
| 沒有安裝且目標可接受 | 取得同一 installation gate 後再次檢查，開始新操作 | 可安裝 |
| Marker 未發布，殘餘可證明屬於本次或已中斷操作 | 使用者明確選擇清理／重試；gate 下確認舊操作已停止，只清理其 ownership 範圍，成功後再開始新操作 | 清理中、可重試，或 cleanup 失敗及下一步 |
| Payload 已提交，OS integration 未完成 | 同一 coordinator 透過 Windows adapter 補完或安全補償 integration；不重建 venv、不重新切換版本 | 整合未完成；成功後才顯示完整「已安裝」 |
| 完整且相容的既有安裝 | 提供啟動與既有 About 更新入口 | 已安裝，無需重複安裝 |
| Runtime／launcher 不相容，或首次啟動失敗 | 顯示原因、可再次啟動／取得診斷及第 6.2 節的保留資料重裝路徑 | 已安裝但啟動失敗，或需要維護；不偽裝為未安裝 |
| Ownership 不明、安裝 identity 衝突或舊操作無法確認已停止 | 安全拒絕；保留資料與去敏診斷，提供具體支援步驟 | 不可安全清理；不要求手動遞迴刪除資料夾 |

Ownership 必須在第一個副作用前持久化；中斷後的處理透過同一 coordinator／adapter 讀取，不能由 Setup 目錄存在與否猜測。新的 cleanup 不得清除晚到或較新操作的檔案。每條恢復路徑都有有界等待、終止結果與明確下一步；不無限重試。

### 7.2 卸載、資料保留與重裝

- 安裝、更新、integration 恢復與卸載共用同一 installation gate。更新進行時卸載安全拒絕並提供稍後重試；V1 不另建跨入口強制取消機制。卸載持有 gate 時，新的更新／安裝必須拒絕；正常啟動 admission 也須避免進入正在卸載的安裝。
- 取得 gate 後重新證明安裝 identity，停止精確的 app 與本安裝相關子行程；不能確認停止時保留 ownership 並回報失敗，不一邊更新一邊刪除。
- 刪除範圍由安裝 ownership 契約決定，包含後續 managed update 建立的 versions 與本安裝專用 runtime。不得假設 Inno Setup 原始檔案清單涵蓋更新產物，不用 wildcard 清空未知目錄，不建立第二套版本 registry。
- 維護工具與卸載註冊的自我清理順序須在 A 階段定義；清理失敗保留可重試入口，不能先移除入口再留下無法處理的殘餘。
- 預設保留 shared 中的 API key、設定與使用者資料；卸載文案明確列出保留範圍。刪除資料是獨立明確選項，僅刪本安裝有 ownership 證據的資料，不遞迴清空 shared root。
- Gate 驗證更新後卸載、保留資料重裝、缺少／損壞 app venv 時的維護入口，以及重裝後設定仍可使用。Shared bytes 比對限定在沒有預期 app 寫入的階段；有正常寫入時記錄與核對預期差異。

### 7.3 診斷與暫存生命週期

失敗保留 installation operation identity、階段、錯誤碼、工具 exit code 與經去敏的原因；區分空間不足、權限、缺少 runtime／DLL、驗證失敗、環境準備失敗及 cleanup 失敗。Setup 提供明確重試或取得診斷入口，不只顯示「準備環境失敗」。

日誌不得記錄 API key、provider credential 或使用者內容；工具輸出先去敏，避免無限制保留完整 stderr／環境變數。診斷匯出使用明確 typed intent，失敗安裝也要能取得日誌，V1 不建遙測平台。

Coordinator 決定 transaction ZIP／staging 的完成後與失敗後保留、清理時機，adapter 執行 operation-scoped cleanup。驗收恢復證據不會提早被刪、成功後暫存可清除，以及清理失敗仍有可理解的結果。不得刪除 verifier／runtime 的正式固定工具目錄。

## 8. 分階段交付與驗收

| 階段 | 產物 | 完成條件 |
| --- | --- | --- |
| A1：契約與發行條件確認 | ownership／恢復狀態表、prerequisite 表、相容範圍、維護責任與出口、ADR、簽署可行性 | 每條失敗有下一步；完成定義與同一 gate 明確；簽署身份資格、CI 與 timestamp 可行；離線／權限承諾可交付 |
| A2：乾淨 VM 技術 gate | 有界封裝 spike 與 runtime／verifier／維護入口證據 | 無系統 Python、Git、OpenSSH；斷網安裝與啟動；離開 Setup、清除暫存、重開機後仍可啟動，恢復網路後可更新；驗證最小保留資料重裝路徑，決定最低 Windows／架構 |
| A3：新手流程確認 | 最小流程原型／既有設定頁與少量新手觀察 | 使用者能辨識下載入口、provider／費用需求、找到設定與第一個 Action；先修正阻塞認知問題。此階段不宣稱完整 Setup 產品驗收通過 |
| B：共用首次安裝協調 | typed intent、snapshot、ports 與唯一 coordinator | 依最新使用者指示先完成隔離本機候選；重用現有 install engine；正常／取消／晚到、integration 部分完成與 admission 測試通過；中斷／跨 session 仍需裝置驗證；UI 無檔案安裝政策 |
| C：使用者入口 | Setup、stable launcher 捷徑、最小首次使用入口、卸載 integration、去敏診斷 | 不需命令列；完成狀態真實；新使用者明確觸發 Action 取得結果；既有與殘餘安裝安全拒絕／恢復；更新與卸載互斥、保留 API key／資料重裝成功 |
| D：CI/CD 接入 | 固定版本 Setup asset、簽章、稽核清單、量測紀錄與候選資產 | 在既有 bundle gate 後組裝 Setup；驗證 Setup 版本／payload identity 與簽章後建立 draft；保留 ZIP／catalog assets；正式公開發布需 E gate 通過 |
| E：發行驗收 | 最終候選檔的瀏覽器下載／clean-VM／新手 evidence 與資料比對 | 下載信任狀態明確；安裝 v1→離開 Setup／重開機→stable launcher 啟動→設定／首個 Action→About 更新 v2→注入失敗回滾→卸載／保留資料重裝；確認舊版本及資料契約 |

每階段獨立可回退。Source 啟動不改造成第二個 managed installer；Setup 若未達 gate，不發布該入口。

測試矩陣必須包含中文／空格／長路徑、一般使用者權限、空間不足、重複點擊／兩個 Setup 並行、缺少 verifier/runtime、錯誤 CPU 架構、篡改 ZIP／manifest／簽章、test key、斷電式中斷、取消、殘餘 cleanup、integration 部分完成、首次設定與啟動失敗。另覆蓋無系統工具／斷網、清除 Setup 暫存／重開機、prerequisite 缺失／重開機需求、更新與卸載並行、runtime 不相容出口、更新後卸載及保留資料重裝。部署封裝必須走真實 VM，unit doubles 不能作為新電腦可安裝的證據。

最終候選 asset 的瀏覽器下載測試必須使用與擬發布檔案相同的 hash／簽章，記錄 Windows build、帳號權限、相關防護設定、提示與結果；候選檔若再修改或重新簽署，需重新驗證受影響的 gate。新手第一個結果使用明確 intent；需要真實 provider 的產品驗收與離線技術驗收分開。

每個候選版本記錄 Setup 大小、安裝峰值空間（包含 launcher／version venv、ZIP、staging、runtime 與 prerequisite）、完成後空間、階段耗時與總耗時，包含暫存和正式目標所在磁碟。A2 先量測、C／E 鎖定支援條件與可接受門檻；目前不填入未實測數字，也不以下載大小推估磁碟需求。只有數據顯示封裝成本阻塞首次成功，才評估 launcher 精簡或其他封裝優化。

新手驗收先以少量未使用過 ClipAI 的人做人工觀察，記錄完成／卡住的步驟、取得第一個結果的時間及所需協助。這是探索證據，不當成有代表性的流失率；不新增事件追蹤平台。

## 9. ADR 摘要與 review trigger

Context：managed 更新能力已存在，首次安裝缺可信且自足的使用者入口。

Decision：增量新增完整 Setup 與首次安裝協調，維持 shared verification／materialization／stable launcher／health 契約。

Alternatives：online bootstrap、source BAT、全 app freezing。此期不選。

Consequences：Setup 較大，需維護 bootstrap runtime、維護出口與 Windows 簽章；可避免首次依賴系統工具且保持版本可重現。最小首次使用、診斷及保留資料重裝納入 V1，避免把技術完成誤當產品成功；完整自動修復與 runtime 自動升級暫緩。

Review trigger：新增第二個安裝入口、repair、多 channel、launcher key rotation／runtime 更新或跨架構支援時，檢查是否出現第二個 lifecycle／ownership 機制；bootstrap 工具安全更新須有自己的發行路徑，不能假設 app ZIP 會更新它。

## 10. 未決事項與參考

已建立 A1 ownership／恢復契約、ADR、prerequisite 表與 A3 walkthrough；已下載並核對 python-build-standalone 3.12.14 tag 20260901 與 Win32-OpenSSH preview 的固定實驗資產。本機 copied-runtime／離線 builder／Tcl 探針及既有 namespace signer／verifier 探針通過，並完成 unit／architecture 與既有 managed-bundle smoke。這些不代表正式 bootstrap 或完整 installer 已驗證。

2026-10-01 再完成隔離 source snapshot 的組合探針：固定 runtime／verifier、空 PATH 下，既有 engine 能安裝 signed synthetic bundle 並建立 version／launcher、state／marker。實測該路徑需要 `packaging`；現有 `main.py` 提前載入桌面依賴並因缺少 `yaml` 中止。正式 bootstrap 採 focused app composition 入口並共用 engine，將固定 `packaging` artifact／hash／license 納入封裝；不因入口依賴問題改寫 installer 或 freezing 整個 app。開發 snapshot 不作正式來源，A1–A3 gate 維持未完成。

本期仍未執行乾淨 VM／重開機驗收、未取得正式 Authenticode publisher／簽署方案、未完成可散布 runtime 的全 native notices／簽章 admission，也未取得真人 A3 觀察。候選 runtime python.exe 未簽章，需驗證 final native signing inventory 與 Smart App Control；OpenSSH 候選為 preview，不直接採為正式選型。依最新使用者授權先交付本機候選，以上是公開發行前必須補齊的 gate。

2026-10-01 本機候選實作使用固定 runtime/verifier 與 41 個精確 lock/hash wheel，完成 ClipAI 3.7.8 全依賴離線版本及 launcher venv。Setup 使用獨立 `ClipAI Preview` 安裝／shared／Start Menu／HKCU identity、不修改 PATH、不自啟、不自動發送 provider 請求。Manifest 由每次 build 的獨立本機 Ed25519 authority 簽署，私鑰封裝前刪除；不是官方 publisher 或正式更新 channel。正常啟動從安裝目錄解析 verifier，新 ownership 安裝缺少該工具時 fail closed。

同一 gate 已擴充為 Global namespace；本機一般使用者路徑已驗證。舊 Local namespace writers 的正式遷移與跨 Windows logon session contention 尚待驗證；Preview 新 root 沒有舊 writer，不假稱已解決正式部署混用問題。

Native inventory 已核對 archive 與所選解壓檔的 bytes：runtime-copy profile 48 個 native 中 44 個未簽章，含 venv redirector；verifier-only 的 ssh-keygen.exe／libcrypto.dll 均 Valid。既有 synthetic installation 的 launcher／version venv 啟動器與未簽章 redirector hash 相同。正式簽署納入 redirector，分開記錄上游來源與最終簽署後 hash。Verifier-only 四檔目錄（兩個 native 加 LICENSE／NOTICE）的 signature probe 已通過；不安裝 OpenSSH server／service。完整 license component mapping、正式 verifier 選型及 clean-VM admission 仍未完成，詳見 [inventory evidence](../evidence/first-install-native-inventory-20261001.json)。

具體產物與證據：

- [A-stage validation／prerequisites／walkthrough](first-install-a-stage-validation.md)
- [First-install ownership／recovery contract](../contracts/first-install-contract.md)
- [ADR-0020](../adr/0020-first-install-bootstrap-and-recovery.md)
- [本機執行證據與剩餘 gate](../evidence/first-install-a-stage-20260930.md)
- [2026-10-03 實際 Preview Setup 驗收證據](../evidence/first-install-preview-20261003.md)
- [Preview 安裝與手動驗收](first-install-preview-acceptance.md)
- [2026-10-03 r2 console／Gemini 診斷與驗證](../evidence/first-install-preview-bugs-20261003.md)

V1 以 Windows x64、完整離線 Setup、per-user 固定路徑、保留 shared 資料、非自啟作為基準。候選限定 Windows 11 x64；正式最低支援版本、runtime／verifier 選型、簽署方式與資源門檻仍依實證定案。本機可手動驗收；公開發行仍需完整來源 admission、乾淨 Windows VM 與 publisher 簽署條件，不以本機通過代替。

### 10.1 ROI 與延後範圍

| 項目 | V1 取捨與理由 |
| --- | --- |
| 最小首次使用入口、第一個有效結果 | 納入；低至中成本，直接避免安裝成功後仍無法開始使用 |
| 離開 Setup／重開機後自足性 | 納入；避免整批新電腦無法啟動與更新，gate 投資價值高 |
| 恢復狀態表、同一 gate 卸載、保留資料重裝 | 納入；降低資料風險與人工支援成本，不擴成通用 repair |
| Runtime／launcher 維護契約與最小出口 | 納入；避免相容性／安全修補死結，完整自動維護引擎延後 |
| Prerequisite 表、下載信任與簽章可行性 | 納入；早期即可發現權限／離線承諾無法成立或發行入口受阻 |
| 空間／時間量測、去敏診斷、人工新手觀察 | 納入；成本低，支持封裝取捨並縮短故障定位 |
| 完整 repair／自動自癒、大型 onboarding、遙測平台 | 延後；狀態／測試與維護成本高，目前最小入口及恢復可處理主要風險 |
| Silent install／MSI／企業部署 | 延後；沒有需求證據，會增加權限與支援矩陣 |
| ARM64／全機安裝／任意安裝路徑 | 延後；每項增加發行及 VM 成本，先穩定 x64 per-user 路徑 |
| Online／offline 雙入口、多 channel、獨立更新平台 | 延後；容易形成第二套 bootstrap／policy，沒有證據支持 |
| 全 app freezing 或提前重做 launcher | 延後；先取得資源與可靠性量測，只有阻塞首次成功才評估 |

### 10.2 參考

- Python Windows distribution 說明：https://docs.python.org/3/using/windows.html
- Inno Setup non-admin 設定：https://jrsoftware.org/ishelp/topic_setup_privilegesrequired.htm
- Inno Setup 額外卸載檔案與 wildcard 限制：https://jrsoftware.org/ishelp/topic_uninstalldeletesection.htm
- Microsoft SmartScreen reputation 與簽章限制：https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation
- WebView2 離線／per-user 部署：https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution
- 既有契約：`docs/contracts/managed-update-contract.md`
- 既有 Provider Settings：`docs/PROVIDER_SETTINGS.md`
