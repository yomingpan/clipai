# About 軟體更新：可行性研究與受管理安裝規劃

- 狀態：研究與架構決策草案
- 日期：2026-08-31
- 範圍：Windows、目前的 Python source installation；不修改 production code

## 1. Executive judgment

**分類：Red。Primary recommendation：incremental migration。信心：高。**

About 裡的更新按鈕是可行的，但不能把它實作成「UI 直接啟動 BAT，BAT 在目前目錄下載 GitHub source ZIP、覆蓋全部檔案、重跑 pip、重啟」。這條路同時缺少單一 workflow owner、可驗證的 release payload、managed/user file 邊界、Windows process handoff、power-loss recovery 與 rollback boundary；它也可能覆寫 `.env`、`data/`、使用者修改過的 `config/` 或開發者尚未提交的 source checkout。

唯一建議的主介入是：**逐步把 end-user installation 遷移為受管理、side-by-side 的版本目錄；由 app 內單一 `SoftwareUpdateCoordinator` 管理意圖與狀態，由不位於目前 app tree／`.venv` 的穩定 external updater 準備候選版本、原子切換 current pointer、健康檢查及回滾。** BAT 最多是薄 handoff shim，不能擁有更新規則。

這不是重寫 ClipAI，也不要求立刻改成 PyInstaller。目前 repo 沒有 PyInstaller spec 或 executable installer；現有 wheel、Python 3.12 bootstrap 與 constraints 可以演進為第一版 managed bundle。但 **release asset、manifest、完整性驗證、stable launcher/updater 與 shared-data path 分離完成前，About 應只支援 check／開啟 release page，不應自動套用更新。**

最重要的語意釐清：

- **ClipAI 軟體版本**目前是 `pyproject.toml` 的 project version，About 透過 `importlib.metadata.version("clipai")` 讀取已安裝 distribution metadata。Python 官方文件把這個 API 定義為「installed distribution package version」；它不是 Python interpreter 的版本。[Python `importlib.metadata`](https://docs.python.org/3.12/library/importlib.metadata.html#distribution-versions)
- **Python runtime 版本**目前由 bootstrap 固定為 CPython 3.12。重建 `.venv` 可以確保 dependency 與 ClipAI metadata 一致，但不會把 Python 自動升成別的 minor；只有 release policy 明確改變 required interpreter 時才升級 runtime。
- 目前是 editable install；只改 source file 通常立即生效，但改 `pyproject.toml` 的 version／dependencies 等 metadata 必須重新 install，這也是 About 版本不應靠覆蓋 `pyproject.toml` 後立刻宣稱完成的原因。[pip local project installs](https://pip.pypa.io/en/stable/topics/local-project-installs/#editable-installs) [PEP 660](https://peps.python.org/pep-0660/)

## 2. Triggering evidence：事實與推論

### 2.1 已觀察的 repo 事實

| 面向 | 目前事實 | 更新設計含意 |
| --- | --- | --- |
| App version | [`pyproject.toml`](../../pyproject.toml) 是 `3.7.0`；[`container._application_version()`](../../ClipAI/app/container.py) 讀 installed package metadata | 更新成功驗證必須重新 install 並檢查 metadata，不是只檢查 source file |
| Windows install | [`run_clipai.bat`](../../run_clipai.bat) → [`bootstrap_windows.ps1`](../../scripts/bootstrap_windows.ps1) → [`bootstrap.py`](../../scripts/bootstrap.py) | 目前是 source checkout，不是 immutable installed app |
| Python environment | root `.venv`，固定 Python 3.12；fingerprint 只涵蓋 `pyproject.toml` 與 `constraints/windows.txt` | inputs 改變會 refresh dependencies，但沒有 app payload transaction 或 rollback |
| Install mode | `pip install -e <project-root>` | code 與 running tree 綁定；metadata change 仍需 reinstall |
| Release build | [`.github/workflows/release.yml`](../../.github/workflows/release.yml) build wheel/sdist、smoke-install wheel，然後用 `actions/upload-artifact` 保存 workflow artifact | Actions artifact 不是 updater 可依賴的 published Release asset |
| Release publish | [`docs/RELEASE_CHECKLIST.md`](../RELEASE_CHECKLIST.md) 要先人工下載 workflow artifact、clean-machine smoke，再人工 publish GitHub Release | `releases/latest` 在人工 publish 前可能 404；publish 後仍未保證有 updater asset |
| Live GitHub state | 2026-08-31 查詢 [`releases/latest`](https://api.github.com/repos/yomingpan/clipai/releases/latest) 回傳 `v3.6.5`、`immutable: false`、`assets: []` | 現在有 latest release metadata，但沒有可下載且可驗證的 managed asset；local dev `3.7.0` 也不得降級成 `3.6.5` |
| About UI | [`about.py`](../../ClipAI/ui/about.py) 已有 disabled「檢查更新」按鈕；UI 目前只送 `CloseAbout`／`OpenGitHub` | 按鈕應送 typed intent，不應執行網路、pip 或 subprocess |
| Mutable state | `.env`、`data/`、`logs/`、`diagnostics/` 是 runtime/user-owned；`.venv` 是 disposable | manifest 必須排除並保存這些 path |
| Config | `config/` 同時包含 shipped Actions/language packs/defaults，也包含可能被使用者調整的 app/provider/TTS settings | 在 ownership 拆分前，整個 `config/` 不能被無條件覆蓋 |
| Existing lifecycle | [`main.py`](../../main.py) 有 single-instance gate；`AppRuntime.stop()` 負責 listener、workers、provider transport、owned process 等 shutdown | updater 必須請求正常 shutdown，不能先 kill process 再改 tree |

GitHub 官方將 workflow artifact 定義為 workflow run 的產物，預設 retention 為 90 天；GitHub Release 則是可供使用者下載的 deployable software iteration。兩者用途與生命週期不同。[Workflow artifacts](https://docs.github.com/en/actions/concepts/workflows-and-actions/workflow-artifacts) [artifact retention](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/remove-workflow-artifacts) [About releases](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)

### 2.2 推論

- 現有 bootstrap 很適合被重用為「candidate environment preparation」的起點，但不適合同時成為 release discovery、下載驗證、tree replacement、rollback 與 UI state 的 owner。
- 「覆蓋全部檔案確保一致」的目標是對的；錯的是覆蓋目前 active tree。更可靠的等價做法是：**在空的 candidate directory 內完整 materialize 並驗證所有 managed files，然後只原子切換一個小 pointer。**
- 因為 Python venv 被官方視為 disposable 且不可搬移，candidate 應重建自己的 `.venv`，不能複製或跨版本共用舊 `.venv`。[Python `venv`](https://docs.python.org/3/library/venv.html)
- 現有 relative paths 讓 shipped config、user data 與 working directory 耦合；managed updates 之前必須注入明確 `ApplicationPaths`，否則 rollback 可能回到舊程式卻讀到已被新程式不可逆改寫的 state。

## 3. Current capability and protected behavior

更新設計必須保留以下已驗證行為：

1. `run_clipai.bat` 能在一般 Windows 使用者權限下找到或安裝 Python 3.12、準備環境並啟動 ClipAI。
2. constraints 變動時，bootstrap 會 refresh dependencies；不相容 `.venv` 會被改名保留，而不是直接刪除。
3. About 顯示的是 installed ClipAI distribution version；diagnostics 也使用同一版本來源。
4. `.env` 的 provider credential/model、`data/` 的 preferences/styles/feedback/archive、logs、diagnostics 都不能因 app update 消失。
5. 正常 shutdown 會先釋放 hotkey、provider networking、worker、WebView child process、single-instance lease，再結束 process。
6. 所有使用者動作要立即顯示真實 lifecycle：checking、available、downloading、preparing、ready、restarting、success 或 failure；不能在 download/install 尚未完成時顯示成功。
7. UI 只發出 typed intent 與 render projection；network、filesystem、pip、native process handling 仍是可替換的外部接縫。
8. source checkout、worktree 與有 local modifications 的開發環境必須保持由 Git／開發者管理，不能被產品 updater 覆寫。

## 4. Four-part architecture diagnosis

### 4.1 單一 owner 是誰？

目前不存在 software update workflow owner。建議新增下列 ownership，且每項只有一個 owner：

| State／decision | Single owner | Boundary |
| --- | --- | --- |
| Check/download/apply operation identity、legal transitions、cancellation、user-visible projection | `SoftwareUpdateCoordinator` | `services`; 只依賴 `core` typed contracts |
| 安裝是否為 managed、current/candidate/previous version、release channel policy | `InstallLayout`／update policy contract | immutable core model；由 `app` 注入實況 |
| GitHub HTTPS、ETag、status/rate-limit mapping、asset stream | `GitHubReleaseCatalogAdapter` | external adapter（建議 `platform`） |
| Staging、manifest/file hash、safe extraction、journal、pointer swap、rollback | stable external updater | app tree 與 active `.venv` 外 |
| Worker scheduling、command routing、updater process launch、shutdown admission | focused `SoftwareUpdateRuntimeModule` | `app` |
| About button、progress/error/retry／Install & Restart rendering | About presenter/view | `ui` |
| Shipped config、shared state、secret/log/data paths | injected `ApplicationPaths` composition | `app` 組裝；stores 只接 resolved path |
| Release bundle construction/signing/publishing | release workflow + release checklist | CI/release engineering |

BAT 不持有上述任何 state。它只能以固定、完整路徑啟動 stable launcher/updater，轉傳 opaque operation/request file path，並回傳 exit code。

### 4.2 Reusable capability 還是 special exception？

這是 reusable application lifecycle capability，不是 About 特例。未來 tray menu、啟動後低頻檢查、repair、rollback、channel selection 都會需要同一組 release discovery、operation identity、install layout 與 transaction semantics。若把規則藏進 `AboutDialog` 或 BAT，第二個入口一定會複製狀態機。

### 4.3 哪些 knowledge 正在跨越不該跨的 boundary？

- UI 不應知道 GitHub API URL、asset filename、pip、`.venv` 或 install root。
- GitHub adapter 不應決定「是否允許 downgrade／prerelease／source checkout update」。
- services 不應知道 PowerShell、Win32 file locking、process handles 或 `MoveFileEx`。
- updater 不應解析 product workflow 或 provider config；只接受已驗證的 update request/manifest。
- release workflow 不應假設 Actions artifact 等於 Release asset。
- versioned payload 不應包含 mutable user state；shared state migration 不應由 file copy wildcard 決定。

### 4.4 哪個 enforcement 防止回歸？

1. Typed `CheckForSoftwareUpdate`、`DownloadSoftwareUpdate`、`ApplySoftwareUpdate` 與 operation-scoped completion commands。
2. Architecture tests：`ui/` 禁止 `httpx/requests/subprocess/pip/zipfile/shutil`；`services/` 只依賴 `core`；只有 `app` composition 注入 concrete update adapters。
3. Release schema validation：tag、package metadata、manifest version、asset filename/version、commit SHA 必須一致。
4. Manifest allowlist/denylist gate：不得包含 `.env`、`data/`、`logs/`、`diagnostics/`、`.venv/`、`.git/` 或 updater/launcher current files。
5. Fault-injection tests 覆蓋每個 journal phase，驗證 crash/power-loss 後只會啟動 old 或 fully prepared new version。
6. CI 必須證明 published GitHub Release 有 immutable、signed、digest-bearing managed asset；只有 workflow artifact 時 release gate 失敗。
7. Managed-install marker 是 apply admission 的必要條件；source checkout／unknown layout fail closed。

## 5. Debt multiplier

主要 debt multiplier 是 **duplicated ownership + boundary leakage + unmanaged concurrency + mutable-file classification drift**。

如果現在先加一個一次性 BAT，接下來三個類似變更的成本會倍增：

1. 加 tray「更新」入口時，會複製 check/download/pending state，兩個 UI 可能同時啟動更新。
2. 加 rollback/repair 時，BAT、bootstrap 與 app runtime 會各自維護 current version、environment readiness 與 restart truth。
3. 加 beta channel或自動背景檢查時，GitHub prerelease/version policy 會滲進 UI、script 與 release workflow，難以驗證 downgrade/replay/late completion。

最危險的不是檔案 copy 本身，而是沒有一個 owner 能回答「現在是哪個 operation、active version 是誰、哪些檔案屬於 user、候選是否完整、切換是否已 committed、new app 是否真的 healthy」。

## 6. Realistic options

| Option | Benefit | Cost | Risk | Reversibility | Decision |
| --- | --- | --- | --- | --- | --- |
| A. BAT 直接下載 source ZIP 並覆蓋 current root | 最快看到 demo | 低起始成本 | 極高：partial tree、file lock、user-data overwrite、無真實 rollback、source checkout 毀損 | 低 | Reject |
| B. 在 current tree 下載後逐檔 `os.replace`，保留 backup | 可改善單檔原子性 | 中 | directory transaction 仍非原子；新舊 module/config 可混合；running interpreter 仍鎖檔 | 中低 | Reject |
| C. 只做 check + 開 release page，維持人工更新 | 安全、很快 | 低 | 沒有自動套用；使用者摩擦仍在 | 高 | 可作 Phase 1 暫時能力，不是最終主方案 |
| D. **受管理 side-by-side install + external updater + atomic pointer + health rollback** | consistency、rollback、可測、未來可擴展 | 中高，需先建立安裝與資料邊界 | 初期工程量與 signing/release pipeline 較大 | 高；舊版本保留 | **唯一 primary intervention：incremental migration** |
| E. 立即改成 MSI/MSIX/PyInstaller 自帶 updater | Windows 發佈模型較成熟 | 高；改變整個 packaging/runtime | scope 太大，且不能由現有 evidence 證明必要 | 中 | Defer；不是本次主介入 |

## 7. Recommended intervention

### 7.1 Smallest boundary

先建立一個 vertical slice：

```text
About button
  -> typed update intent
  -> SoftwareUpdateRuntimeModule
  -> SoftwareUpdateCoordinator
       -> UpdateCatalog port (check only)
       -> UpdateInstaller port (prepare/apply external transaction)
  -> UpdateProjection
  -> About presenter
```

`SoftwareUpdateCoordinator` 建議持有一個 operation at a time：

```text
idle
  -> checking
  -> up_to_date | update_available | check_failed
  -> downloading
  -> verifying
  -> preparing
  -> ready_to_restart | preparation_failed
  -> handoff_pending
  -> restarting
```

`restarting` 後 app process 會結束；真正 terminal truth 寫入 updater journal。新 app 啟動後讀取並顯示一次 `updated_to` 或 `rolled_back` 結果。任何 stale completion 必須以 update operation ID 拒絕。

明確 exclusions：不做 silent forced update、不更新開發 worktree、不從 branch/main 更新、不支援 downgrade、不把 beta/prerelease 混入 stable channel、不在第一版刪除所有舊版本、不自動改寫 user config/schema。

### 7.2 Managed installation layout

建議 per-user、無需管理員的 layout：

```text
%LOCALAPPDATA%\Programs\ClipAI\
  launcher\              # stable, not inside a version tree
  updater\               # stable updater host + pinned verification key
  install-state.json     # atomic current/previous pointer, no secrets
  versions\
    3.7.0\
      app\               # immutable shipped resources/config
      .venv\             # disposable environment for this version
      install-manifest.json
    3.7.1\
      ...
  staging\<operation-id>\

%LOCALAPPDATA%\ClipAI\
  state\                 # preferences, personal styles, archive, feedback
  secrets\               # .env replacement or protected credential store
  logs\
  diagnostics\
  update\update-journal.json
```

pointer file與 journal 要在同 volume 建 temporary file、flush，然後以 same-directory replace commit。Windows `ReplaceFile` 可用 replacement file 取代原檔並選擇建立 backup，且要求 replacement/replaced/backup 在同一 volume；`MoveFileEx` 也支援 replace 與 write-through。這些原語適合小 state/pointer file，不代表能原子替換一個 non-empty active directory。[ReplaceFile](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-replacefilew) [MoveFileEx](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-movefileexw)

### 7.3 Installation identity and source-checkout exclusion

只有同時滿足以下條件才能 apply：

- stable launcher 提供的 signed/verified `managed_install_id`；
- resolved executable、current pointer 與 version root 都位於同一受管理 root；
- version directory manifest 與 installed distribution metadata 一致；
- current install 不是 editable/direct source checkout；
- update mutex 可取得，沒有另一個 prepare/apply transaction。

若 marker 缺失、有 `.git`/worktree 痕跡、distribution `direct_url.json` 表示 editable、路徑不在 managed root，或狀態互相矛盾，About 顯示「此安裝由 source/Git 管理；請使用 Git 或下載 managed installer」，只允許開 release page。不要嘗試靠 `git status` 自動決定是否可覆寫，因為 end-user 機器不一定有 Git，而 unknown layout 應 fail closed。

### 7.4 Shipped files 與 user-owned files

release manifest 只管理：Python app/wheel、main entrypoint、versioned `config` defaults/actions/language packs、constraints/hashed requirements、assets、bootstrap contract 與 schema migration code。

永遠排除：

- `.env`／credential；
- `data/`、archive、feedback、personal styles、preferences；
- `logs/`、`diagnostics/`、temporary audio；
- `.venv/`、pip cache；
- `.git/`、worktree metadata、untracked files；
- current launcher/updater 與 active transaction journal。

目前 `config/` 混合 shipped product resources 與可能 user-adjusted settings，因此 Phase 0 要先做 file-by-file ownership inventory。建議把 canonical defaults 留在 version tree，把 user overrides 轉成 typed settings store 放 shared state；遷移完成前，不能對既有 source install 宣稱全自動更新安全。

### 7.5 Release/discovery contract

Stable channel 使用 public `GET /repos/yomingpan/clipai/releases/latest`。GitHub 定義 latest 為依 `created_at` 排序的最近 non-draft、non-prerelease release；public resource 可不帶 authentication 呼叫。[GitHub Releases REST API](https://docs.github.com/en/rest/releases/releases#get-the-latest-release)

client 必須：

- 固定 owner/repo 與 GitHub API host；設定 explicit User-Agent、connect/read timeout、bounded redirects、maximum response/asset size；
- 支援 `ETag` conditional request 與 bounded retry/backoff；未驗證 public request rate limit 是每 IP 60/hour，因此只能 explicit user check 或低頻 cache，不能 UI polling。[GitHub REST rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api) [REST best practices](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api)
- 把 404（尚未有 published release）、403/429（rate limit）、5xx、offline、timeout、invalid JSON 分成 typed failures；
- 解析 PEP 440 version，要求 `tag_name == "v" + manifest.app_version`，只在 candidate > installed 時 offer；不得用字串比較。PEP 440 明訂 numeric release segment 以數值排序，並可正規化前綴 `v`。[Python version specifier standard](https://packaging.python.org/en/latest/specifications/version-specifiers/)
- latest 沒有合格 asset 時顯示 release pipeline incomplete，不 fallback 到 branch archive。

目前 `v3.6.5` release 的 `assets` 是空陣列，所以 GitHub 自動產生的 `zipball_url` 只能作人工 fallback，不能作 production managed update。GitHub 的 integrity verification 明確說 generated source ZIP/tarball 不能用 `gh release verify-asset` 驗證，因為它們是請求下載時才建立。[Verifying release integrity](https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/secure-your-dependencies/verify-release-integrity)

### 7.6 Managed release asset

每個 release 要先建立 draft，附加完整 assets，再 publish；若 repository 啟用 immutable releases，publish 後 tag 與 assets 不可修改，並自動產生 release attestation。這是 GitHub 建議的 immutable release workflow。[Immutable releases](https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases) [Managing releases](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository)

建議 asset：

```text
clipai-windows-x64-3.7.1.zip
clipai-windows-x64-3.7.1.manifest.json
clipai-windows-x64-3.7.1.manifest.sig
```

manifest 至少包含：schema version、app version、release tag、commit SHA、target OS/arch、required Python、minimum updater version、payload byte size、每個 file path/size/SHA-256、entrypoint、config/state schema compatibility、rollback compatibility 與 release timestamp。

GitHub Release asset API 會提供 asset size、download URL 與 `digest`（例如 SHA-256）；download 後必須先核對 size/digest，再解析內容。[Release assets REST API](https://docs.github.com/en/rest/releases/assets)

但 API digest 與 asset 從同一 GitHub trust boundary 取得，只能可靠偵測傳輸／disk corruption；完整自動執行前仍應驗證由 stable updater 內 pinned publisher key 驗證的 detached manifest signature，或以可在 end-user host 真正驗證的 GitHub release attestation。GitHub 明確指出 attestation 必須驗證 cryptographic signature、timestamp 與 signer identity 才有安全效益。[Artifact attestations REST API](https://docs.github.com/en/rest/users/attestations)

若第一版沒有 signing/attestation verifier，就保持「check + 使用者開 release page」；不要把 HTTPS + hash 說成 publisher authenticity。

ZIP extraction 前要拒絕 absolute path、`..`、drive/UNC path、duplicate/case-colliding path、symlink/reparse entry、reserved device name、超過 manifest 的 file、解壓後超過 size/file-count budget。Python 官方也警告不可在未檢查內容前解壓 untrusted archive。[Python `zipfile`](https://docs.python.org/3/library/zipfile.html#zipfile.ZipFile.extractall)

### 7.7 Reproducible environment preparation

對 managed end-user deployment，不再用 editable install。pip 官方把 regular local install 建議給 CI/deployment，editable install 定位為 development install。[pip local project installs](https://pip.pypa.io/en/stable/topics/local-project-installs/)

可靠候選環境流程：

1. release build 產生 ClipAI wheel 與 Windows x64/Python 3.12 wheelhouse；
2. dependencies 全部 pin + SHA-256；拒絕 sdist；
3. 在 `staging/<operation-id>` 驗證並解開 payload；尚未建立 venv；
4. 把已驗證 payload materialize 到尚未被 `current` 指向的最終 candidate path，例如 `versions/3.7.1`，並寫入 `preparing` marker；
5. **直接在這個最終絕對路徑**建立全新 `.venv`，之後不得移動或改名該 version directory；
6. `pip install --no-index --find-links <wheelhouse> --require-hashes --only-binary :all:`，再 regular-install ClipAI wheel；
7. smoke：import `ClipAI`、import `main`、load every config/language pack、確認 `importlib.metadata.version("clipai") == manifest.app_version`、確認 `sys.version_info` 符合 manifest；
8. 全部成功後以 atomic marker replace 將 candidate 標成 `prepared`；失敗則保持 `current` 不變，並由 journal 驅動清理或重試。只有後續 pointer commit 才讓 candidate 生效。

這個順序刻意不 rename 含 `.venv` 的 parent directory。若同版號的 final
candidate path 已存在但不是已驗證的 `prepared` generation，recovery 必須先依
journal 判定它是可重用、可清理或應隔離的 incomplete generation；不得在原處混入
第二次 preparation。

pip 官方說 wheelhouse 可以在 index unavailable 時安裝並避免現場 compile；hash-checking mode 要求全部 dependency 被 pin 且有 hash，用來抵禦 remote tampering/network issue。[pip repeatable installs](https://pip.pypa.io/en/stable/topics/repeatable-installs/#using-a-wheelhouse-aka-installation-bundles) [pip secure installs](https://pip.pypa.io/en/stable/topics/secure-installs/)

這裡的「重建環境」更新的是 ClipAI installed metadata 與 dependency set；Python interpreter 仍是 manifest 要求的 3.12。只有 required Python 改變時才由 stable bootstrap 安裝新 interpreter，並一樣建立新的 candidate venv。

### 7.8 Process handoff

updater 不能從即將替換/刪除的 `.venv` 或 version tree 內執行；Windows 要移動/替換的 file 必須先關閉，active interpreter、DLL、WebView/helper process 可能仍持有 handle。[Windows moving and replacing files](https://learn.microsoft.com/en-us/windows/win32/fileio/moving-and-replacing-files)

建議 protocol：

1. App 明確收到 `Install & Restart` intent，coordinator 建 transaction ID。
2. `app` 以 absolute path 啟動 stable updater，禁止 command string concatenation，且不繼承不必要 handles。
3. Updater 取得 global update mutex、驗證 signed request、回報 `handoff_ready`。
4. App enqueue 正常 `ShutdownApplication`，完成 runtime cleanup；不以 `TerminateProcess` 取代 lifecycle。
5. Updater 等待 app **process handle** signaled，而不是固定 sleep 或只輪詢 PID。Windows process 結束後 process object 會變成 signaled；`WaitForSingleObject` 可等待該 handle。[Terminating a process](https://learn.microsoft.com/en-us/windows/win32/procthread/terminating-a-process) [WaitForSingleObject](https://learn.microsoft.com/en-us/windows/win32/api/synchapi/nf-synchapi-waitforsingleobject)
6. Updater 最後重驗 current pointer/operation ID，commit pointer，從 stable launcher 啟動 candidate。
7. Candidate 在完成 config load、single-instance acquire、runtime start readiness 後，以 named pipe/event 或 atomic health file 回報 version + transaction ID。
8. Updater bounded wait；正確 ack → finalize；timeout/crash/wrong version → rollback pointer 並重啟 previous。

如果只做 script prototype，PID + creation-time guard 可以暫時模擬，但 production host 應使用 process handle。BAT 啟動 batch file本身也必須經 command interpreter；Microsoft 的 `CreateProcess` 文件同時提醒要用完整 executable path並避免錯誤 quoting/search path。[CreateProcess](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-createprocessw)

### 7.9 Transaction、atomicity 與 rollback

Journal phase：

```text
discovered
downloaded
verified
candidate_prepared
shutdown_requested
pointer_committed
candidate_launched
candidate_healthy
finalized
rolled_back
```

不變量：

- `current` 永遠指向 previously healthy 或 fully prepared candidate；
- pointer commit 前 failure 只刪 staging，不影響 active version；
- pointer commit 後、health ack 前 failure 一律切回 previous；
- previous version 至少保留到 candidate healthy 且 shared-state migration 被確認 rollback-compatible；
- cleanup 永遠在 finalize 之後，而且不能刪 current/previous/updater；
- journal write、pointer write 與 migration backup 都要 atomic；每一步 idempotent，重跑不重複 destructive work；
- reboot/relaunch repair 讀 journal，不從「哪些 directory 看起來存在」猜狀態。

Shared state migration 必須是 transactional：先 backup、再 migrate；若 candidate 未 healthy，還原 backup。更理想的是用 expand/contract schema，讓 previous 版本能忽略新欄位，直到 rollback window 結束才做不可逆 migration。

不要把 `MOVEFILE_DELAY_UNTIL_REBOOT` 當一般更新路徑：它需要較高權限，且 API return 只能代表 registry scheduling 成功，不能代表 reboot 時真正 move 成功。[MoveFileEx delayed operations](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-movefileexw)

### 7.10 Threat and reliability model

| Failure／threat | Required control | User-visible outcome |
| --- | --- | --- |
| Offline、DNS/TLS、timeout、GitHub 5xx | bounded timeout/retry、保留 cached state、不改 install | `檢查失敗，可重試` |
| API 404／latest 尚未 publish | typed `no_published_release` | 說明可開 release page，不當成 up-to-date |
| Latest release 沒有 managed asset | fail closed | `此 release 尚未提供自動更新檔` |
| Truncated/corrupt download | `.part`、size + digest + per-file hash | 不解壓、不切換 |
| Malicious archive path/zip bomb | path/type/count/size budgets、extract to empty staging | `更新檔無效` |
| Compromised mirror/network | pinned repository/hosts、manifest signature/attestation | authenticity failure；不允許 override |
| Compromised GitHub publisher/repo | offline-held/pinned publisher key、protected immutable release workflow | 阻止只靠 account takeover 替換 asset；key compromise 另有 rotation/revocation plan |
| Downgrade/replay/prerelease | PEP 440 compare、stable channel policy、minimum accepted version | 不 offer downgrade |
| Source checkout/uncommitted files | managed marker admission；unknown/source layout check-only | 絕不覆寫 |
| Disk full／ACL／AV lock | preflight free-space、same-volume staging、bounded retry | active version繼續運作 |
| App/child process still alive | normal shutdown + process-handle wait + timeout | 不切 pointer；可取消/重試 |
| Power loss at any phase | atomic journal/pointer + idempotent recovery | old 或完整 new，不能 mixed tree |
| Candidate import/config/env failure | offline smoke before commit | preparation failed；old app 不停 |
| Candidate crash after launch | health timeout + rollback pointer/relaunch previous | 顯示 rolled back |
| Shared schema incompatible | migration backup/compatibility declaration | rollback 恢復 state |
| Duplicate clicks/concurrent instances | single operation ID + update mutex | 第二次 intent 顯示已進行，不啟第二個 updater |
| Updater self-update | A/B updater slot或下一次啟動切換，永不覆蓋 running updater | 延後生效；保留 old host |

若未來發佈 executable updater/launcher，應使用一致 publisher identity 簽署。Microsoft 說 SmartScreen 會參考 publisher/file reputation；未簽檔案每一版都要重新累積 reputation，而簽章本身仍不保證完全沒有首次警告。[SmartScreen reputation](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation) SignTool 可驗證檔案是否自簽署後未被修改且來自 trusted source。[SignTool verification](https://learn.microsoft.com/en-us/windows/win32/seccrypto/using-signtool-to-verify-a-file-signature)

### 7.11 Observable completion criteria

介入完成的客觀條件：

- managed clean install 能從 release asset 安裝並顯示正確 ClipAI package version；
- source checkout 的 About 永不修改檔案，只提供 release link/manual instructions；
- 任一 fault injection point crash 後，restart 只會得到 old healthy 或 new healthy version；
- `.env`、data、logs、diagnostics 的 byte/hash 與 schema符合 migration contract；
- active app/updater/version dir 沒有互相覆蓋；
- update check/download/apply 的 pending/success/failure 皆與真實 operation identity 一致；
- release pipeline 缺 asset、signature、manifest、immutability 任一項時，自動 apply gate 失敗；
- rollback 後 previous app 能啟動並讀取 user state；
- 沒有 production update subprocess/network/filesystem code進入 UI。

## 8. Reversible migration sequence

### Phase 0 — contracts and inventory

1. 建立 `ApplicationPaths` 與 managed-install identity contract。
2. 盤點 `config/` 每個檔案：shipped canonical、user override、generated state 三類；把 `.env/data/logs/diagnostics` 明確移到 shared root。
3. 定義 update manifest、journal、health ack、signature 與 rollback compatibility schema。
4. 寫 architecture/fault-model tests，production updater仍 disabled。

回退方式：只新增 typed paths/contracts；仍可用現有 launcher與source install。

### Phase 1 — safe check-only About UX

1. About button送 `CheckForSoftwareUpdate(operation_id)`。
2. 加 GitHub latest adapter、PEP 440 compare、ETag/cache、typed failures。
3. managed asset/signature 不完整時只開 GitHub release page。
4. source checkout 永遠 check-only。

回退方式：feature flag關閉 button，原 About／GitHub link不變。

### Phase 2 — release contract

1. CI 對 tag 建 wheel、Windows/Python 3.12 wheelhouse、hashed requirements、managed ZIP/manifest/signature。
2. draft release attach assets後再 publish；啟用 immutable releases。
3. release checklist驗證 tag/package/manifest/installed metadata一致、asset digest/signature、offline clean install。
4. GitHub Actions dependency固定 full commit SHA；GitHub 官方指出完整 SHA 是 action reference 的 immutable pinning方式。[GitHub Actions secure use](https://docs.github.com/en/actions/reference/security/secure-use#using-third-party-actions)

回退方式：保留舊 workflow artifact；managed apply gate不開。

### Phase 3 — managed installer/launcher

1. 建 stable launcher/updater root與current pointer。
2. 首次 managed install從 release bundle建立 version dir + venv；把 current user state一次性搬到 shared root，保留 backup。
3. launcher固定從 pointer resolve entrypoint與working directories。
4. 只有 managed install顯示 `Download and install`。

回退方式：保留原 source directory與state backup；managed install可完整移除而不改source checkout。

### Phase 4 — side-by-side update and rollback

1. external updater在app仍運作時 download/verify/prepare candidate。
2. ready後explicit `Install & Restart`，走 process-handle handoff、pointer commit、health ack。
3. fault injection、Windows smoke、rollback/state migration matrix全過才 enable。

回退方式：feature flag降為check-only；previous version/pointer保留。

### Phase 5 — hardening and optional updater self-update

1. A/B updater、publisher key rotation/revocation、stale staging GC、retention policy。
2. 觀測 failure code與匿名 aggregate前需另做privacy decision；不可包含 API key/path/content。
3. 評估是否值得改用 MSIX/MSI/PyInstaller；這是新的 review trigger，不是本計畫前置條件。

### 8.1 Test and release evidence plan

### Unit / sims

- version table：equal/newer/older、`v` prefix、pre/dev/post、malformed、local dev 3.7.0對release 3.6.5不得降級；
- discovery：200/304/404/403/429/5xx/timeout/truncated JSON/no asset/wrong asset/multiple asset；
- coordinator每個legal/illegal transition、stale operation completion、cancel/duplicate click；
- managed-install detection：marker/path/direct_url/source checkout矛盾時fail closed；
- manifest：path traversal、UNC/drive、case collision、duplicate、symlink/reparse、missing/extra files、size/hash mismatch；
- journal recover table：每個phase前後crash，重跑idempotent；
- pointer commit／rollback與wrong health ack；
- config/state classification denylist；
- migration success/failure/rollback與old-reader compatibility；
- package version與Python version是兩個獨立assertion。

### Architecture tests

- UI 只能emit commands/render projection；
- services 不import GitHub/httpx/subprocess/zipfile/Win32；
- external adapter不能決定product version/channel policy；
- app只有一個 update runtime module與一個 coordinator；
- BAT 無 network/pip/copy/delete/version comparison，只啟動stable host；
- updater不位於managed version dir或`.venv`；
- manifest禁止user-owned paths。

### Integration sims

- local fake release server + throttled/aborted stream；
- 真實 ZIP與temporary same-volume install root；
- fake old/new child processes與health handshake；
- offline wheelhouse install；
- disk-full/permission/file-lock/fault injection adapter；
- two simultaneous app/update processes只允許一個transaction。

### Windows release smoke

- Windows 10/11、x64、長路徑/Unicode username、corporate proxy/CA、Defender/AV；
- active Tk/WebView/TTS/provider worker shutdown後不留鎖；
- app在download/preparation期間仍可用，restart階段有清楚feedback；
- kill app/updater、拔網路、任意journal phase模擬power loss；
- new app錯誤、health timeout、rollback/relaunch previous；
- `.env`、data、logs、diagnostics保留；
- installed `clipai` metadata == manifest version，`sys.version_info` == required runtime；
- clean machine不需Git或GitHub CLI，除非兩者被正式列為installer dependency。

### Release gates

1. Windows CI全套 tests + architecture tests + language-pack gate。
2. tag = `v{pyproject version}` = wheel metadata = manifest version。
3. manifest commit SHA = tag target；所有payload hashes重算一致。
4. asset signature/attestation在clean host驗證成功。
5. release assets先完整attach，再publish immutable release。
6. public latest endpoint回傳正確asset、size、digest、immutable flag。
7. offline candidate install與startup smoke成功。
8. source checkout check-only smoke與managed update/rollback smoke都有日期證據。

## 9. Concise ADR

**Context**

ClipAI目前從mutable source checkout與root editable `.venv`執行；About已有update placeholder。現有GitHub workflow artifact不是穩定published update asset，且app tree混有shipped config、user state與runtime files。Windows active process也不能安全覆蓋自己正在使用的tree。

**Decision**

採用per-user managed side-by-side installations。`SoftwareUpdateCoordinator`是in-app update lifecycle唯一owner；stable external updater在version tree/venv外準備完整候選、驗證signed manifest、atomic commit current pointer、等待new-version health ack並在失敗時rollback。BAT只作thin handoff。Source checkout永遠不自動apply。

**Alternatives rejected**

直接BAT whole-tree overwrite、current tree逐檔replace、以GitHub generated source ZIP作production payload、立刻全面改MSI/MSIX/PyInstaller。

**Consequences**

增加stable launcher/updater、release signing、wheelhouse、path ownership與migration工作；換得no mixed-version tree、可重現environment、可測crash recovery、user-data preservation與確定rollback。

**Review trigger**

若stable updater本身頻繁需要更新、Python runtime升級造成bundle過大、企業政策阻擋自建updater、或三次以上Windows signing/locking/support問題影響交付，重新評估MSIX/MSI或bundled executable distribution；不因目錄看起來複雜就重寫core。

## 10. Uncertainty and open questions

目前缺少的最高價值證據：

1. 最終發佈對象是少數可信使用者、公開consumer，還是enterprise？這決定signing/SmartScreen與silent update標準。
2. 是否接受per-user `%LOCALAPPDATA%\Programs\ClipAI` managed install，或必須保留任意自選source folder？後者不應支援unattended apply。
3. `config/config.yaml`哪些欄位正式允許user edit？需逐欄決定default vs override及migration owner。
4. Release signing key/attestation要用何種verifier？若沒有可在clean machine獨立驗證的方案，apply gate應保持關閉。
5. Python 3.12 runtime是由全機Python Manager共用，還是未來bundle/embed？目前計畫沿用Python Manager；embed會改變bundle與patch責任。
6. Candidate `healthy`的最低標準是config load + runtime started，還是需要hotkey/tray/WebView/provider readiness？建議不把外部provider credential/network當rollback gate。
7. Shared data migration是否已有跨版本backward compatibility policy？沒有的話，第一版只允許不變或可逆schema。
8. 更新時是否允許app繼續執行到candidate prepared？建議允許，以降低停機；final pointer switch才shutdown。

最高價值的下一個inspection不是再寫BAT，而是做兩個throwaway spikes：

- 在temporary root驗證stable launcher + two version dirs + atomic pointer + health rollback；
- 在clean Windows VM驗證draft immutable release asset、detached signature/attestation、offline wheelhouse install。

兩個spike都通過後，才把Phase 1 check-only往Phase 4 automatic apply開放。
