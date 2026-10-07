# 首次安裝 A 階段執行證據

開始：2026-09-30；候選資產探針完成：2026-10-01（Asia/Taipei）。
範圍：開發者本機。A1–A3 整體 gate 未通過，沒有正式 Setup 產物。

## 已完成

- A1 ownership／取消／提交／恢復／卸載契約與 ADR-0020 已記錄。
- Prerequisite、runtime／verifier 固定候選與新手 walkthrough 已記錄；沒有改動
  production `ClipAI`、main 或 release workflow，也沒有修改 `.tmp/` 原有內容。
- 新增可重跑的候選下載、runtime 與 verifier 探針，全部位於
  `experiments/first_install`，不作為正式 installer／release admission。
- 固定下載檔的大小與 SHA-256 核對成功；下載 ZIP／tar 解壓前檢查路徑與 link。

## 本機條件

Windows version `10.0.26200.0`，64-bit OS，一般使用者，未以管理員啟動。
本機有 Codex 提供的 Python 與系統 OpenSSH，故不符合「沒有系統工具」的 VM
條件。探針只對子行程使用空 PATH 與白名單環境，沒有停用 OS 網路。
.NET Framework registry 顯示 Release `533509`／Version `4.8.09221`；這不證明
別台電腦已有相同 runtime。CIM OS inventory 被環境拒絕，OS version 改以
Environment API 讀取；沒有因此跳過或假造 clean-VM gate。

PATH 查詢沒有取得 Inno compiler、SignTool、VBoxManage、vmrun 或 Get-VM。
CurrentUser certificate store 沒有找到目前有效且含 private key 的 code-signing
certificate；未查閱／改動遠端帳號或簽署服務，也不推論所有發行者都沒有憑證。

## 固定輸入與 runtime 探針

| 項目 | 輸入與實測 |
| --- | --- |
| 初步開發來源 | Codex base Python 3.12.14；copied runtime 50,214,406 bytes；28.130 秒；僅探索，不可作產品散布來源 |
| 上游 runtime 候選 | python-build-standalone tag `20260901`，`cpython-3.12.14+20260901-x86_64-pc-windows-msvc-install_only_stripped.tar.gz` |
| Runtime archive identity | 21,980,728 bytes；SHA-256 `7c45c9622400d578709a9b2cddbe8124cc21d382409d9f13406d706d28e31b14`，與官方 GitHub release metadata 相符 |
| 候選 runtime 實測 | Python 3.12.14／win-amd64／64-bit；Tcl 8.6.12；OpenSSL 3.5.8；排除 site-packages 的 copied runtime 48,629,446 bytes；19.144 秒 |
| Runtime executable identity | SHA-256 `1a967738a234a3bd90e8fa8b925e20a994326e1eb8b74913026a9449a933e6db`；本機 Authenticode 結果 `NotSigned` |
| 實際行為 | 中文／空白目錄、空子行程 PATH、venv、ensurepip、hashed offline synthetic wheel installation、新 candidate 行程、base/executable identity、Tcl 初始化均通過 |

時間為本輪本機 wall-clock，不是平均／p95、正式 app 安裝 SLA 或磁碟峰值。
Runtime bytes 是複製後選定 runtime 檔案總量，不是 Setup 或整體安裝所需空間。
探針的 fixture distribution 名為 clipai，但不含真實 app；全依賴、Tk window 與
trusted bootstrap 仍為 `not_covered`。

Runtime archive 內有 Python／Tcl/Tk notices 與 pip licenses。尚未完成所有 native
components 的來源／license 清單核對，不宣稱產品 redistribution admission 通過。
候選 python.exe 沒有 Authenticode 簽章；需把實際要執行的 exe／DLL／pyd 的
Windows 信任狀態納入 final signing inventory 與 Smart App Control gate，不能
假定只簽 Setup 就足夠。此主機可執行探針，不代表 SAC 開啟的乾淨電腦可執行。

## Verifier 探針與保留的失敗證據

輸入為 Microsoft 維護的 Win32-OpenSSH `10.0.0.0p2-Preview` 的
`OpenSSH-Win64.zip`；5,704,583 bytes，SHA-256
`23f50f3458c4c5d0b12217c6a5ddfde0137210a30fa870e98b29827f7b43aba5`。
固定輸入核對成功，ssh-keygen.exe 本機 Authenticode 結果為 `Valid`，exe hash
`b51fdd26be0f7c83398d18e5354a0acb0406a9de25516791758fe63bbe3ae870`。
已找到 LICENSE／NOTICE。這是 preview 相容性實驗，不採為正式 verifier 選型。

第一次最小環境探針失敗：key generation exit `255`，沒有 stderr；不是簽章
成功。縮小變因後發現只保留 SystemRoot 等而缺少 `PROGRAMDATA` 時，工具連
usage 都以 `255` 退出；加回 `PROGRAMDATA` 後 usage 可執行，加回 USERPROFILE
則無法修復。最終白名單保留這個 OS 位置，沒有傳入 provider credentials。

同一 production signer／verifier、空子行程 PATH 下最終通過：Ed25519 key
generation、既有 `clipai.managed-update.manifest.v1` namespace 簽署／驗證、
篡改拒絕及 production policy 拒絕 TEST_KEY_ID。測試 private/public keys 已由
所屬操作移除；報告不含 key material，並保留最初 failed report。

下載行程以 Windows `mkdtemp` 建目錄時產生了受限 ACL，普通驗證行程不能讀取。
已將已驗證產物複製到新的工作樹目錄供驗證，未修改系統 ACL 或刪除原檔；下載
探針改為 UUID + exclusive mkdir 繼承 workspace ACL。此處僅是開發工具修正，
不把此權限模型當成產品 per-user installer 驗證。

## 測試結果與未完成 gate

### Native／notice inventory（2026-10-01）

新增 read-only inventory，先核對固定 archive size／SHA-256，再以 archive 原始
member bytes 核對所選 unpacked native／notice 檔案，最後用 Windows
`Get-AuthenticodeSignature` 清查。不執行候選程式、不安裝 OpenSSH 服務、不修改
檔案簽章；保留 UUID 報告並移除含本機絕對路徑的 signature input 暫存。

| Profile | Native 檔案 | 本機 Authenticode | Notice 檔案 |
| --- | --- | --- | --- |
| Runtime copy（排除 site-packages） | 48 | 44 NotSigned／4 Valid | 3 個獨立文件；ensurepip bundled pip wheel 內另找到 1 個 notice |
| Verifier-only | 2 | ssh-keygen.exe／libcrypto.dll 均 Valid | LICENSE.txt／NOTICE.txt |

Runtime 的 Valid 檔案為 tcl86t.dll、tk86t.dll、vcruntime140.dll、vcruntime140_1.dll。
未簽章包含 root python.exe／pythonw.exe／Python DLLs、venv redirector、OpenSSL
DLLs 與多個 pyd。清單包含 runtime-copy profile 所帶的測試 pyd，沒有據此新增
runtime 裁切方案；正式封裝應以實際交付／載入的檔案重新驗收。

本機先前 synthetic installation 的 version 與 launcher `.venv/Scripts/python.exe`
均與 `Lib/venv/scripts/nt/python.exe` SHA-256 相同：
`3b5cc4150dc98800ee46b09034187bb2d8ba3c8ea3368d3a46e9bb42876b58db`。
Version venv 的本機 signature 狀態也是 NotSigned。不能只檢查 root python.exe
或 Setup；venv 啟動器也必須納入 final signing／clean-VM gate。

Verifier-only profile 不包含 sshd、service installer、agent 或其他 OpenSSH CLI。
已從核對過 hash 的來源複製兩個 native 與 LICENSE／NOTICE 到新的四檔目錄，
重跑既有 verifier probe：有效簽章、篡改拒絕與 production test-key 拒絕均通過，
fixture 私鑰已移除。再用該目錄重跑隔離 bootstrap probe，既有 engine 的 signed
synthetic bundle 安裝也通過。本機所測路徑可使用這個封裝範圍；OS DLL closure、
clean VM、正式 verifier 選型與 native admission 仍待驗證。

Notice 檔案存在與 hash 相符不表示已完成 component/license mapping。Stripped
archive 未提供此次清查可用的完整組件映射；Python LICENSE 內的第三方參考也
不能直接當作每個 native DLL 均已涵蓋的證據。Full app wheels 與 packaging 的
notices／native inventory 未納入這輪。Authenticode Valid 只是此主機檢查結果，
不代表最終發行檔在 Smart App Control／乾淨 VM 中通過。

完整相對路徑、size、hash、signature status 與 notice 清單見
[native inventory](first-install-native-inventory-20261001.json)。

### Bootstrap 組合探針

2026-10-01 完成 bootstrap 組合探針：在固定候選 runtime、copied verifier、空 PATH、
`python -I` 子行程中，使用開發 source snapshot 跑既有 release builder、verifier、
filesystem installer、Windows gate 與 offline candidate builder。Signed synthetic
bundle 的 version 與 launcher 均成功建立，state revision 0／version 與安裝 marker
identity 核對通過，launcher keyring 已存在；本輪耗時 35.579 秒。

未帶 packaging 的 baseline 在 imports 階段以 `ModuleNotFoundError: packaging`
失敗；明確加入開發 snapshot `packaging 26.2` 後，實際載入的外部 Python imports
只有 `packaging`。既有 `main.py` 的 import-only probe 則缺少 `yaml`，沒有啟動 app。
這支持 focused bootstrap composition 入口，但不是所有 launcher／maintenance
入口、真實 app 或正式 bootstrap 的完整 dependency closure。

Source snapshot SHA-256：
`a81c7c4fc1dfb7c3314d2b1968b4ecbf6093e66f77dbeacc73f8d972491f9efd`。
它是本輪排序後 Python source 名稱與內容的 fingerprint，不是 signed release
manifest。測試 fixture 私鑰已移除。前兩輪因 fixture entrypoint／transaction ID
接線錯誤而失敗，報告保留；它們不是上游工具或 production engine 的缺陷。
Clean VM、跨 logon session、native signing、全 app、更新與卸載均未覆蓋。

| 驗證 | 狀態 | 範圍 |
| --- | --- | --- |
| Probe／inventory unit + architecture | 通過，71 tests | 環境隔離、拒絕 venv／重疊來源、舊 evidence 保留、archive traversal、profile／notice 清查及變更 unpacked 檔案拒絕、架構約束 |
| 完整預設 unit suite | 通過，1,844 tests，46 deselected | 此輪本機；integration 是獨立 gate |
| 既有 managed-bundle integration smoke | 通過，1 test | 真實本機離線 builder／簽章／identity-bound health fixture；不是正式 Setup 或 clean VM |
| 固定上游 runtime／verifier 本機探針 | 通過 | Synthetic runtime fixture／canonical signature，沒有 provider 呼叫 |
| 隔離 bootstrap 組合探針 | 通過 | 空 PATH、固定 runtime／verifier、既有 engine、signed synthetic bundle；開發 source／packaging snapshot，非正式 bootstrap |
| Archive-bound native／notice inventory | 通過 | Runtime 48／verifier-only 2 native 檔案；來源匹配及本機簽章清查，非 redistribution admission |
| Verifier-only signature／bootstrap probes | 通過 | 四檔獨立目錄、signature policy 與既有 installer；無 OpenSSH server／service，仍是本機 synthetic fixture |
| A1 整體 gate | 未完成 | 最終 runtime notices／native signing inventory、正式 verifier／publisher signing 選型尚缺 |
| A2 clean VM／reboot／full app／uninstall | 未覆蓋 | 需要乾淨 VM、正式封裝與完整 dependency evidence；不得以本機通過替代 |
| A3 真人新手流程 | 未覆蓋 | Walkthrough 已備妥，尚無真人觀察 |

完整機器可讀快照見 [local candidate evidence](first-install-local-candidates-20261001.json)。
原始工具報告與候選 bytes 保留在 git-ignored `artifacts/first-install-*`，不進入
release assets。尚未達 A1–A3 gate，不進入 B／C，不發布 installer。

## 外部條件

需要可供操作的乾淨 Windows 11 x64 VM，以及實際 publisher 的個人／公司身份、
註冊國家與可用 code-signing 方案。所在地不是從時區推斷；若 publisher 在台灣，
Microsoft 現行 Artifact Signing Public Trust eligibility 不能直接假定適用。
參考與後續驗收步驟見 [A-stage validation](../specs/first-install-a-stage-validation.md)。
