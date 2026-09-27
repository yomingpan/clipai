# Inline Dictation 自主循環驗證規劃（`Ctrl+Alt+M`）

狀態：實作與驗證進行中；已有型別命令旅程 runner、多 seed 晚到事件、實際 Paste／Clipboard owner 的受控模擬、Paste 終態 identity 固定案例、discard 後 Paste 的 mutation oracle、完整文字 UI 測試、內容安全階段 trace 與 machine-readable manifest。離線量測工具可分模式及原文／潤稿彙整、驗證 trace 順序並比較同 cohort；尚無可宣稱的裝置基線。受控 Tk 文字目標及內容安全讀回協定已建立，已與正式 ClipAI 在使用者桌面完成 Choice／Minimal 原文、Choice／Minimal 潤稿及 Minimal 取消的五輪受控 smoke；獨立 HID／loopback 音源與完整桌面矩陣仍待完成。2026-09-27 在使用者可見的 Windows 桌面執行固定 runner：快速層 363 項、Tk 桌面層 13 項、真實 WebView2 層 4 項均通過，manifest 為 `artifacts/inline-validation-interactive/manifest.json`。WebView2 測試 profile 與頁面需放在繼承 `%LOCALAPPDATA%` 權限的隔離目錄；pytest 的受限 `tmp_path` 曾造成控制器啟動失敗。取消錄音會等相符引擎終態或 watchdog 才關閉狀態視窗。完整桌面矩陣、獨立按鍵／音源觀察及裝置基線仍為 `not_covered`。與[量測規劃](inline-dictation-measurement-plan.md)共用情境、互動 identity 與結果語彙，但品質判定與延遲分析分開。缺少的桌面證據不能判成通過。

## 核心判斷

發版前需要一個能反覆執行、重現失敗、並對**真實使用者旅程**做判定的驗證迴圈。它先在可控接縫大量跑狀態與競態案例，再在隔離的 Windows 桌面上少量跑真正的畫面、麥克風、焦點、貼上及還原。兩層共用案例描述與預期結果，但各自標示證據等級。自動化不能靠觀察「視窗關了」或「Ctrl+V 已送出」就宣稱文字已插入。

驗證優先序：**不能貼錯或取消後仍貼上；不能遺失使用者內容與剪貼簿；每個操作都有真實可見的回應；最後才比較速度與文案品質。** 延遲資料依量測規劃統計，不讓快但錯誤的案例進入成功分布。

## 一個案例的契約

每個案例宣告：起始環境與目標、起始時凍結的 Inline Input Mode、語音片段或辨識事件、使用者操作序列、故障注入點、預期可見狀態、預期外部副作用、終態、逾時上限、清理條件及可重現 seed。操作應描述語意（第一次快捷鍵、第二次短按／長按、完整模式選擇原文／潤飾、Esc、切換目標或 tray 模式），再由不同 runner 對應到 controller command 或真實 UI。不得在案例裡直接改動私有狀態以製造「通過」。

每一步同時檢查三種 oracle：

- **領域 oracle：** 接受／拒絕、唯一 owner 的狀態與 identity、合法轉移、最多一次 provider/Paste、舊 completion 不影響新互動。
- **使用者 oracle：** 控制項與訊息在正確時機可見；等待、失敗、取消與終態符合實際操作；Esc 後沒有暗中副作用。畫面測試讀呈現結果，不以內部 snapshot 代替畫面。
- **外部 oracle：** 受控目標取得的確切文字、游標／選取範圍、目標視窗、原剪貼簿各格式是否還原、麥克風 track 是否釋放。對一般第三方 App，只能宣告 Paste Dispatch，不能以 OS 注入回傳值推論已接收。

每個案例執行前後必須重設受控目標、clipboard、provider fake、時鐘與事件佇列；檢查沒有殘留錄音、worker、視窗、provider task、Paste membership 或逾時 callback。清理失敗時停止該桌面 runner，避免污染後續案例。

### 可重播模型

案例定義使用有限 action grammar：`start`、`stop_short`、`stop_long`、
`choose_raw`、`choose_refine`、`change_mode`、`escape`、`foreground_change`、`engine_event`、
`provider_event`、`paste_event`、`advance_time`、`shutdown`。每個 action 都具備
前置 phase、可控延遲、目標 interaction/operation identity 及預期結果。reference
state model 只表達 ADR-0019 的公開 phase、identity 關係、允許副作用與 terminal
truth；runner 將語意 action 映射到 typed command、fake port 或受控桌面操作。

每個 seed 會產生合法流程與刻意非法的重複、倒序、過時事件。縮小器移除不影響
失敗的 action，留下最短反例。固定 invariant 為：每個 interaction 至多一次
provider admission、至多一次 Paste admission、discard 後零 Paste、terminal
ack 只影響相同 identity、Paste Dispatch 後不宣稱撤銷成功、以及每輪清理後無
active resource。這讓多 seed 探索的是明確狀態模型，不只是重複執行測試腳本。

## 情境目錄（首批）

| 類別 | 模擬的使用者旅程與變化 | 必須證明 |
| --- | --- | --- |
| 基本流程 | 完整模式：第一次快捷鍵→聆聽→第二次快捷鍵→選原文／潤飾；極簡模式：短按開始→短按結束直接貼原文，或長按結束後潤飾並貼上 | 一次操作只有一次貼上；raw 不呼叫 provider；極簡正常流程不開選擇窗；潤飾使用最後確認的內容；終態真實。 |
| 口述內容 | 短句、長段、無聲、只有 interim、連續 final、改口、重複、專有名詞、中英混用、兩種支援語言 | 不漏片段、不重複貼上；不確定處保留；AI 品質由固定語料另行審核。 |
| 啟動與時間 | 冷／暖啟動、麥克風權限等待、快速連按、停止早於 `Listening`、120 秒限制、stop watchdog | 開始／停止回應可見；沒有虛假 `Listening`；逾時僅結束所屬 capture。 |
| 選擇與潤飾 | 等待選擇時再按快捷鍵；provider 慢、拒絕、空結果、取消、結果晚到；期間切換 provider 設定或 tray 模式 | 拒絕重入有回饋；模式固定於互動開始；潤飾失敗保留原文並要求明確恢復選擇，不自動貼；取消後晚到結果不觸發貼上。 |
| 目標與焦點 | 啟動後切換視窗、關閉原目標、焦點拒絕、游標／selection 變化、IME、不同 DPI／螢幕、目標自行修改內容 | 不改貼到新的意外目標；焦點失敗有可恢復結果；不承諾無法證明的原游標位置。 |
| 貼上與剪貼簿 | 正常貼上、Paste overlap、modifier 未放開、dispatch 前取消、dispatch 後 Esc、外部同時改 clipboard、還原失敗 | 依 Paste owner 回報 `failed`／`cancelled`／`dispatched_unconfirmed`／`cleanup_failed`；不覆蓋較新 clipboard，不重送造成重複。 |
| 競態與復原 | 相同事件重送／倒序、舊 capture/provider/Paste completion 晚到、視窗關閉後 callback、連續多輪、shutdown | identity 隔離、至多一次終態；無殘留資源；下一輪仍可正常使用。 |
| 可用性與隱私 | 兩種模式各階段的可見文案、鍵盤操作、提示、拒絕與失敗；診斷匯出 | 每次使用者意圖即時有回饋；極簡狀態不搶焦點，失敗才展開恢復；dispatch 提示有可讀停留時間且舊提示不能關掉新互動；沒有假成功；日誌與產物不含語音、逐字稿、prompt 或剪貼簿內容。 |

用 pairwise 組合語言、raw/refine、冷暖、負載、目標與錯誤類別，避免全組合爆炸；上述高風險競態、取消及 clipboard 案例必須逐一固定重播，不能只靠隨機覆蓋。新增真實事故時先加入最小重現案例，再擴充組合。

## Runner 與自主循環

1. **快速旅程 runner（預設／CI）：** 透過現有 typed command、controller 與注入 port 駕駛整段互動；虛擬時鐘控制 deadline；fake engine/provider/Paste 回報可延後、重排、重複及失敗。多個 seed 探索交錯順序，失敗時保存 seed、事件序列與不含內容的狀態差異。此層驗證 policy 和所有權，不聲稱 Windows 裝置效能。
2. **隔離桌面 runner（專用 Windows 主機）：** 啟動正式組裝的 ClipAI、受控文字目標與可控 provider／音源；從 UI 操作選擇並以外部 observer 讀畫面與目標結果。受控目標需提供 exact text、caret/selection、focus identity、multiple clipboard formats、Paste receipt 與 IME composition-settled 的讀回協定。真實 WebView2／麥克風、剪貼簿、焦點、Paste 與螢幕 frame 只在此層驗證。fake STT event cases 驗狀態機；可重播音檔或 loopback microphone corpus 另驗真實音源到 Browser Speech 的鏈路。runner 使用專用桌面與測試設定，失敗後仍執行清理；環境、權限或音源不可用要回報 `blocked`，不能算 pass。

   `scripts/inline_dictation_controlled_target.py` 是這個 runner 的受控文字目標元件。以 `--output`、`--expected-text`（僅用同意的固定測試語料）和 `--run-nonce` 啟動後，它將 `ready`、`paste_observed` 與指令讀回寫入 JSONL。stdin 每行可送出 `{"command":"focus"}`、`{"command":"observe"}`、`{"command":"reset"}`、`{"command":"select","start":"1.0","end":"1.3"}` 或 `{"command":"shutdown"}`。讀回含目標文字 SHA-256／長度／是否與預期完全相同、插入點、selection、Paste 事件次數、前景視窗 identity，以及剪貼簿各格式的雜湊；不輸出文字或剪貼簿內容。目標事件與稍後在背景執行的剪貼簿取樣各有時間戳，不跨程序直接相減。完成一次互動後送 `observe`，再用 `scripts/verify_inline_controlled_target.py EVENTS --scenario delivery|cancel --output REPORT` 判定文字、Paste 次數、焦點及剪貼簿是否符合預期。刻意注入錯文、重複 Paste、錯焦點、晚到 Paste 及剪貼簿未還原都會使此 oracle 失敗；沒有原生前景或讀回時回報 blocked。元件測試只證明讀回協定與判定器，不證明 ClipAI 已成功貼上；正式桌面 runner、畫面 observer、IME settled 觀測與真實音源仍待完成。

   `scripts/run_inline_controlled_desktop.py` 可在使用者可見的桌面引導單輪實體按鍵案例：管理員權限的測試 PowerShell 會使受控目標高於一般權限的 ClipAI，不能代表正常桌面輸入，因此先以 `controlled_harness_elevated` 停止。再以 App 既有單一實例 gate 確認同一 Windows session 有 ClipAI，未啟動便輸出 `clipai_app_not_running`；此檢查不能辨識執行中的版本或工作樹。腳本也檢查工作樹已儲存的 Inline 模式與 `--mode` 相同，不符就以 `inline_mode_mismatch` 停止。接著啟動受控目標、於互動結束後做延後讀回、截取該輪 allowlisted app trace，並要求單一 Inline Interaction、模式、原文／潤稿路徑及相符終態。目標另記錄 Esc keypress 與修飾鍵狀態，App 熱鍵與 runtime 邊界記錄 Esc 是否被接受、忽略或由其他面板處理；這些訊號不記錄文字。報告明示按鍵是操作者陳述，尚無獨立 HID、畫面首幀、IME settled 或音源 observer；單輪通過只能作為受控目標與 app trace 的 attended smoke，不能當裝置基線。2026-09-27 的前兩次取消嘗試 App trace 為 0；第三次 App 已進入聆聽，但截至該輪報告截止仍無取消終態，且剪貼簿在測試期間由未知來源改變，因此不能宣告通過。第四次確認測試 PowerShell 為管理員而 ClipAI 為一般權限。第五次同權限測試中 Esc 導致第一輪 discard 終態，但整個測試包含三輪互動、一次 refine Paste，且 App 當時實際模式為 Choice，故整體失敗不能歸因於單輪取消。

   原文／潤稿 delivery 可用固定語句的 `--expected-text` 驗逐字相等，或以 `--freeform` 驗證原本空白目標確實收到一次非空且保留的文字；後者不驗證語音逐字準確度。2026-09-27 的 Choice 原文單輪在受控目標貼入 157 UTF-8 位元組、目標與剪貼簿檢查通過，使用者回報內容大致符合所說較長語句。原命令仍要求逐字等於「你好」，因此原報告保留 `fail`；以同一份內容安全事件重評的 `artifacts/inline-controlled-raw-choice-1/freeform-assessment.json` 對自由口述 delivery smoke 判為 `pass`，逐字準確度為 `not_machine_verified`。
   2026-09-27 的 Minimal 原文單輪於受控目標收到一次非空貼上，延後讀回及剪貼簿還原均通過；原報告的同時間戳排序錯誤已修正，重評結果見 artifacts/inline-controlled-raw-minimal-1/corrected-report.json。Minimal 取消單輪觀察到一次 Esc、單一 interaction 的 discarded 終態、零次 Paste，且目標與剪貼簿保持原狀；更嚴格的重評結果見 artifacts/inline-controlled-cancel-minimal-1/verified-report.json。Minimal 潤稿單輪的第二次長按在 trace 中標為 long，Provider 潤稿完成後送出一次 Paste；受控目標穩定收到 108 UTF-8 位元組且剪貼簿還原，重評見 artifacts/inline-controlled-refine-minimal-1/verified-report.json。Choice 潤稿單輪有 choice_ready、refine_requested、Provider 完成及一次 Paste，受控目標穩定收到 171 UTF-8 位元組並恢復剪貼簿，見 artifacts/inline-controlled-refine-choice-2/report.json。五輪 raw／refine／cancel 案例已由固定 runner 從原始讀回與 trace 重評；不含逐字準確度、獨立音源／HID、首幀或 IME settled 的證明，也不能建立裝置延遲基線。
   固定 runner 可重複指定 --attended-report，從 target.jsonl 與 inline-trace.log 重新判定每個已保存的桌面案例，再把結果寫入 manifest 的 attended_smoke；舊報告中的 pass/fail 不直接沿用。controlled_paste_target 欄仍指尚未完成的自動化多目標矩陣。重試請使用新的 --output-dir，runner 會拒絕覆寫既有原始證據。
   2026-09-27 代理桌面重跑時快速層 376 項與 WebView2 層 4 項通過；Tk 層在不同案例出現 Tcl 資料檔偶發讀取錯誤，見 artifacts/inline-validation-five-attended-interactive-20260927b/manifest.json。使用者先前在可見桌面完成 13 項 Tk 通過，見 artifacts/inline-validation-interactive/manifest.json；代理後續的 Tk 失敗不應轉寫為產品通過或失敗。
3. **實體快捷鍵接縫：** production listener 會排除注入的鍵盤事件。快速 runner 可由 typed command 駕駛語意，桌面 runner 可驗 UI，但兩者都不能證明實體全域快捷鍵可用。發版矩陣另外使用受控實體 HID 輸入設備或明確的人工操作 gate；不得加入 production 的「接受注入按鍵」後門。此項沒跑就標 `not_covered`。
4. **重播與收斂：** 每次變更先跑固定 smoke，再跑受影響類別與多 seed 競態，最後跑桌面矩陣。失敗自動保存 seed、可重播事件序列、環境版本、trace identity、預期／實際 oracle 差異；快速 runner 縮小隨機序列後轉成固定回歸案例。桌面 runner 只保存受控測試文字的畫面證據，先裁切或遮蔽其他視窗，並保留原始案例步驟供重播。修正後重跑原 seed、鄰近 seed、固定案例與桌面對應情境，不靠盲目重跑直到碰巧通過。

工具應只**觀察**既有 owner 的事件。案例定義、報告與故障注入可在 tests/scripts；不要為測試建立第二套產品 lifecycle、全域事件匯流排、另一個 clipboard/Paste owner，或把測試分支塞入 UI 生產邏輯。桌面測試可更換注入 port 或在隔離環境使用測試 adapter，但不能改變產品的 side-effect admission 規則。

每個 runner 與 oracle 都要有至少一個必跑 mutation test：故意允許 discard
後 Paste、故意忽略 identity、故意將 `dispatched_unconfirmed` 標成成功、或故意
漏還原 clipboard，驗證對應 oracle 必然失敗。runner 自身無法抓到這些錯誤時，
它不具備作為發版證據的資格。

## 結果判定與發版 gate

每輪產出 machine-readable manifest：案例版本、app/OS/WebView2/provider 版本、runner 證據等級、seed、每步結果、終態、清理、量測 trace 連結與 `pass`／`fail`／`blocked`／`not_covered`。`blocked` 與 `not_covered` 不得併入通過率；flaky 案例是待調查失敗，需區分產品競態、測試隔離及外部服務不穩，不能無限自動重試洗掉。必跑矩陣包含指定的代表裝置、受控 Windows/plain-text/browser/rich-editor 目標、兩種模式、短按 raw／長按 refine、兩種支援語言及高風險取消/Paste 情境。未跑的非關鍵必跑項只能由指定 release owner 以風險原因與到期日暫時豁免；豁免不等同通過。錯目標貼上、接受丟棄後貼上、重複貼上、未處理的 clipboard／麥克風清理失敗，以及虛假成功聲稱不可豁免。執行節奏為 PR 跑快速固定案例與受影響矩陣、每日專用 Windows 主機跑桌面 smoke 和多 seed、發版前跑完整指定裝置／目標矩陣與實體快捷鍵 gate。

發版必要條件：固定高風險案例全通過；受控目標無錯貼、取消後貼上或重複貼上；clipboard 與麥克風清理有證據；所有失敗與不確定終態有正確可見回饋；指定必跑裝置／目標矩陣完成，其他未跑項明示。效能門檻按量測規劃建立基線後訂定。真實第三方 App 的相容性、特定硬體麥克風與語意改寫品質仍需人工抽查；自主循環不把它們偽裝成全面自動通過。

相容性分為三層：**Supported** 是每版必跑矩陣中可讀回的目標；
**Observed** 是曾測得 Paste Dispatch、但沒有每版讀回 gate 的第三方目標；
**Unsupported** 包含密碼欄、安全桌面、權限隔離或無法安全取得焦點的目標。產品
只能對 Supported 目標主張受控驗證；Observed 保持 `dispatched_unconfirmed`；
Unsupported 要及早給出清楚限制。

## 實作順序（後續工作）

1. **先鎖契約：** 以 ADR-0019 定案兩種模式、第二次短按／長按、模式凍結、失敗時明確恢復、取消與 Paste Dispatch 分界、可讀終態通知及不可豁免的正確性條件；同步修正 ADR-0018 和術語。
2. **再遷移生命週期：** 延伸單一 controller 至 Paste 終態，加入 typed origin／acknowledgement、identity-scoped provider 取消和 view lease，接上 tray typed mode intent 與兩種呈現；移除舊 callback 驅動貼上與過早關窗路徑。
3. **建立完整旅程證據：** 定義可重播案例與三類 oracle，把現有 unit/sim 接成少量端到端旅程；每個 runner 先以刻意注入的錯誤確認 oracle 會失敗，再擴至多 seed 競態。
4. **驗證真實桌面：** 加入受控目標與隔離 Windows runner，驗證實體快捷鍵、短／長按、焦點、剪貼簿、Paste 終態及通知可讀性。
5. **量測後定門檻：** 建立內容安全的 trace 與代表裝置基線，再產出分層報告和發版 gate；依基線決定是否優化 STT、prompt、provider 或手勢。
