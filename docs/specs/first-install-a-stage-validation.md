# 首次安裝 A 階段驗證

日期：2026-09-30；本機候選探針更新：2026-10-01。狀態：執行中；A1 設計契約已記錄，A1–A3 gate 尚未全部通過。
本文件區分來源事實、本機實測與尚缺的發行／裝置證據。
2026-10-01 使用者要求完成可驗收候選後，B/C 已先實作隔離的 ClipAI Preview。
本文件的 A1–A3 待驗證項目保留為公開發行 gate；不是本機候選交付阻擋。

## A1 決策與 prerequisite 表

已建立 [安裝契約](../contracts/first-install-contract.md) 與
[ADR-0020](../adr/0020-first-install-bootstrap-and-recovery.md)。固定 services
coordinator、共享 install engine、Windows integration 與單一 gate 的責任。
預設根目錄可由既有 managed ApplicationPaths 注入；仍需以正式 Setup 實測。

| 元件 | 用途與 V1 決策 | 偵測／來源與相容條件 | 權限／失敗及待驗證事項 |
| --- | --- | --- | --- |
| Windows x64 | V1 目標；先以 Windows 11 x64 驗證，不宣稱最低支援 build 已定案 | 明確 OS build／CPU 架構 admission；不能只檢查 Python pointer size | 一般使用者；其他架構明確拒絕；最低 build 待 clean VM |
| Python 3.12 + venv + ensurepip + Tcl/Tk | 文字核心與安裝必要；app-local 固定 base runtime | python-build-standalone 3.12.14 tag 20260901 固定候選／hash；本機 minor／win-amd64／Tcl／離線 builder 通過 | 不註冊系統 Python、不改 PATH；完整 notices、native signing 與 clean VM 尚缺，未接受為正式可散布 runtime |
| Managed wheelhouse／lock | App 與 bootstrap 所需 Python dependencies | 沿用 release hashed wheelhouse、`--no-index --require-hashes`；需 native wheel ABI 相容證據 | 不需安裝 compiler／SDK；synthetic wheel 成功不代表完整依賴成功 |
| Ed25519 verifier | 安裝、正常 managed 啟動、更新必要 | 沿用 namespace／format；Win32-OpenSSH 10.0.0.0p2-Preview 固定候選／hash，本機簽署、篡改拒絕及 production test-key 拒絕通過 | 空 PATH 可用，但需 PROGRAMDATA；preview 尚不採為正式選型；保留 LICENSE／NOTICE，完整 native DLL admission 待驗證 |
| VC runtime／native DLL | Python 與媒體 wheels 的 native loading | 分別檢查 Python、miniaudio、pygame 等實際 loading；只隨包帶來源允許重散布的 DLL | 不默默提權；缺失是否可 app-local 解決待 clean VM；不能由本機成功推論 |
| .NET Framework | pythonnet／WinForms 語音 helper | pythonnet 官方 netfx 最低 4.6.1，建議 4.7.2+；V1 clean-VM 先驗證內建 4.8+，不另外安裝 .NET SDK | 若缺失而需要管理員，明確降級／拒絕該能力；不靜默提權；實際 pinned wheel 仍需驗證 |
| WebView2 Evergreen | 目前 Windows browser speech helper | 偵測 per-user／per-machine runtime；真正離線需 Microsoft Standalone Installer，不能使用會下載的 Bootstrapper | 保留共用 runtime；缺失時文字核心是否仍完整可用待實測；不改選固定 major 或新增 browser backend |
| Inno Setup compiler | 僅 build／CI；使用者不需安裝 | 候選 per-user `PrivilegesRequired=lowest`；compiler 版本／hash/license 固定後入封裝 gate | 本機 PATH 尚未發現；尚未安裝或執行正式 Setup |
| Authenticode／timestamp | 官方外部發行必要 | public-trust publisher identity、支援的 CI 簽署服務／憑證與 timestamp，簽署後驗證 | 本機沒有找到可用的 CurrentUser code-signing private certificate；remote signing 未確認 |

Python 官方完整 installer 可帶 venv／Tcl，但其系統安裝／登錄及卸載副作用需要
驗證；NuGet 文件明示沒有 UI tools，不能當作完整 Tk runtime；embeddable 不能
直接替代目前 pip／venv pipeline。App-local python-build-standalone 是候選來源，
不採用 `latest` 作為發行輸入；固定 artifact／hash 已取得並核對，完整 license
與 native signing admission 尚未完成。
現有 Codex runtime 只能作本機探索來源，禁止把它直接當可散布產品依賴。已下載
並核對固定的 python-build-standalone 候選；本機探針通過，但其 python.exe 未簽章，
其他 native components 的 notices／簽章及 clean-VM admission 仍待完成。

新的來源檢查發現：目前 installation mutex 使用 Windows `Local\\` namespace，
同一 installation 跨 logon session 尚未排他。採用既有 gate seam 擴充，不另建
file lock；候選 `Global\\` mutex 的 ACL、非管理員 access 與舊 host 相容性要實測。

## 本機 A2 探針

執行入口：

```powershell
.venv/Scripts/python.exe -m experiments.first_install.probe_runtime --runtime-root <可信且已解壓的完整-Python-根目錄>
```

只在新的 `artifacts/first-install-runtime/runtime-<id>` 範圍複製 base runtime，
排除 site-packages 與 cache，拒絕 venv／junction／symlink，保留每輪獨立結果。
它不下載、不改登錄／PATH、不刪除舊輪次，不呼叫 provider／剪貼簿／麥克風。
子行程 PATH 為空，只帶 OS 必要環境與本輪 temp；沿用正式
`OfflineCandidateEnvironmentBuilder` 建立 Unicode／空白目錄的 venv、ensurepip、
hashed offline pip installation，最後以新行程核對 copied base／candidate identity。
Fixture 名為 clipai 只為滿足既有 builder 的 identity probe，內容是明示 synthetic
runtime marker，不包含真實 ClipAI，不是 signed managed bundle。

JSON report 的 `passed` 僅表示這輪本機探針成功；clean VM、重開機、OS 斷網、
trusted bootstrap、完整 app dependencies、Tk window、簽章／license 與完整
managed 安裝→更新→卸載都明確列為 `not_covered`。Pip 禁止索引不等於 OS 斷網。
不把原始工具輸出或環境值寫入 evidence。白名單保留 PROGRAMDATA 這個 OS
位置；Win32-OpenSSH 缺少它會在產生診斷前退出，不能誤當 signature invalid。

候選下載與 verifier 探針：

```powershell
.venv/Scripts/python.exe -m experiments.first_install.fetch_candidates --component runtime
.venv/Scripts/python.exe -m experiments.first_install.fetch_candidates --component verifier
.venv/Scripts/python.exe -m experiments.first_install.probe_verifier --tools-root <本輪解壓目錄>/OpenSSH-Win64
```

下載只使用 `experiments/first_install/candidates.json` 的固定 URL／size／SHA-256；
不執行下載程式、不安裝服務、不將 preview 自動納入產品。實驗下載與 ownership
receipt 不作為第二套 managed release schema。最終 release 仍共用既有 builder。

本機結果與 gate 狀態保存於 [A-stage evidence](../evidence/first-install-a-stage-20260930.md)。
證據不包含個人環境路徑或秘密。

### Bootstrap 與既有 engine 組合探針

```powershell
.venv/Scripts/python.exe -m experiments.first_install.probe_bootstrap --runtime-root <固定候選-Python-根目錄> --tools-root <固定候選-OpenSSH-根目錄>
```

以新的 source snapshot、copied runtime 與 copied tools，在 `python -I`／空 PATH
子行程直接使用既有 release builder、signature verifier、filesystem installer、
Windows gate 與 candidate builder。Bundle 使用 synthetic app／TEST_KEY_ID；操作
只在本輪 UUID 目錄中建立 version／launcher、state 與 marker，不啟動桌面功能。
測試 private key 在 child finally 與 parent timeout cleanup 移除。

本機實測：未帶 `packaging` 時 import 失敗；明確加入開發來源的 `packaging 26.2`
snapshot 後 engine 全流程通過。本輪外部 Python imports 只有 `packaging`，但不
推論其他入口的 dependency closure。現有 `main.py` import-only probe 缺少 `yaml`，
證明目前安裝 CLI 入口提前載入桌面依賴。正式 bootstrap 應使用 app composition
的 focused 入口，共用 engine；`packaging` 要納入固定來源／hash／license 清單，
不能使用開發環境 snapshot 作為正式封裝來源。

這輪不覆蓋真實 app dependencies、正式可信 bootstrap、跨 logon session 排他、
更新／卸載或 clean VM；報告與前兩輪 fixture 接線失敗均保留，不覆寫舊 evidence。

## Native／notice inventory

Native／notice inventory 可用以下指令重跑，candidate-root 必須包含已下載的
`download.archive` 與 `unpacked`；來源先核對 pinned identity，再清查原始 bytes：

```powershell
.venv/Scripts/python.exe -m experiments.first_install.inventory_candidates --component runtime --candidate-root <runtime-candidate-root>
.venv/Scripts/python.exe -m experiments.first_install.inventory_candidates --component verifier --candidate-root <verifier-candidate-root>
```

本機 runtime profile 48 個 native 中 44 個未簽章，包含 venv redirector；verifier-only
2 個 native 均 Valid。這是固定來源 inventory，不是授權映射完成或正式簽章驗收。
來源與完整結果見 [native inventory](../evidence/first-install-native-inventory-20261001.json)。
已用 verifier-only 四檔獨立目錄重跑 signature 與 bootstrap 組合探針，均通過；
該範圍仍需 clean-VM OS DLL loading 與正式 verifier admission。

## A3 新手流程與觀察準備

本階段先重用既有 Provider Settings 的語意與 walkthrough，不新增另一套設定
policy 或完整 onboarding。以下是驗收腳本，尚未招募／觀察真人，也不標示 A3 通過。

| 步驟 | 最小文案／入口 | 觀察點 |
| --- | --- | --- |
| 下載 | 主要按鈕「下載 Windows x64 安裝程式」；顯示版本與 publisher | 是否選錯 ZIP／wheel；是否能辨識信任提示 |
| 安裝完成 | 「ClipAI 已安裝」與「啟動 ClipAI」；失敗顯示原因／下一步 | 是否誤認安裝等於 AI 已可用 |
| 首次啟動 | 「設定 AI 服務」與「稍後設定」；簡述自己的 API key 與 provider 費用 | 是否知道 key 從哪裡取得及如何返回設定；不要求工程師口頭指路 |
| 設定 | 開既有 Provider Settings，明確按 Validate and Save | 不將驗證失敗說成安裝失敗；沒有隱性計費請求 |
| 第一個 Action | 短句「選取一段文字，按住 Alt 約 0.5 秒開啟選單，再選翻譯」；以實際 shortcut configuration 核對 | 明確觸發後取得有效結果；關閉後知道如何再次使用 |
| 稍後設定／離線／失敗 | 保留可見設定入口與可操作原因 | 不顯示可用 AI 的虛假成功；使用者不需重裝解決 credential 問題 |

後續以少量未使用過 ClipAI 的人觀察卡住步驟、需協助次數與第一個結果耗時，
不保存原文／結果／key、不推算代表性流失率。A3 前期先驗證入口理解；C／E
再以實際下載的 Setup 與明確使用者 intent 驗證整段旅程。

## 未完成 gate 與下一步

1. 固定 runtime／preview verifier 實驗資產已核對且本機探針通過；下一步完成
   notices／native signing inventory、正式 verifier 選型及完整工具依賴 admission，
   不把候選或本機 Codex 副本當成已接受的發行來源。
2. 提供可控的乾淨 Windows VM，驗證無系統工具、OS 斷網、非管理員、重開機、
   正式 app dependency imports、下載信任、update／uninstall／retained-data reinstall。
3. 確認真實 publisher 身份與簽署方案。Microsoft Artifact Signing 的 Public Trust
   個人目前限美國／加拿大，組織名單未含台灣；若 publisher 位於台灣不可直接
   假定適用。也不能以可建立 Azure 資源或 Private Trust 代替 public trust eligibility。
4. 取得真人 A3 觀察；完整 gate 未通過前不進入正式 B／C，不更動 release publish。

上述缺口需要發行資產／外部環境與真實使用者證據，不是新增程式碼可以假造的
完成條件。A1 ownership／恢復契約可先 review；A1 整體 gate 仍未完成。

## 來源（查閱 2026-09-30）

- [Python Windows distributions](https://docs.python.org/3.12/using/windows.html)
- [python-build-standalone distributions](https://github.com/astral-sh/python-build-standalone/blob/main/docs/running.rst)
- [Inno non-admin setup](https://jrsoftware.org/ishelp/topic_setup_privilegesrequired.htm)
- [pythonnet runtime requirements](https://pythonnet.github.io/pythonnet/python.html#loading-a-runtime)
- [WebView2 distribution](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution)
- [Artifact Signing eligibility](https://learn.microsoft.com/en-us/azure/artifact-signing/quickstart#prerequisites)
- [Windows kernel object namespaces](https://learn.microsoft.com/en-us/windows/win32/termserv/kernel-object-namespaces)
