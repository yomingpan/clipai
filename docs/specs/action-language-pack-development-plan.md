# ClipAI Action Language Pack 架構執行規劃

> 狀態：已完成 repo 調查與產品決策訪談，可直接進入實作
> 架構分類：**Yellow**
> 主要建議：**在既有 config composition seam 進行可逆的增量遷移，不重寫 Runtime**
> 信心：高
> 預設語言包：`zh-TW`
> Phase 1 首個新增語言包：`ja-JP`

## 0. 文件用途與執行規則

本文件是實作規格，不是概念提案。實作者應依里程碑順序工作，不要先建立 locale-aware Runtime、通用 i18n framework、UI resource system 或語言分支。

實作前仍須遵守：

- `docs/Product_philosophy.md`
- `docs/ARCHITECTURE_BOUNDARIES.md`
- `docs/TESTING_STRATEGY.md`
- 根目錄 `AGENTS.md`

每個 commit 都必須同時更新 contract、production code 與對應測試。若實作途中發現需要讓 Workflow、Provider、UI widget、Voice Input 或 TTS 讀取 pack locale，先停止；這代表 seam 放錯位置或 scope 已經擴張。

---

## 1. Executive judgment

### 1.1 結論

ClipAI 不需要大型多語言重構。既有執行路徑已經把 Action 設定編譯成 `ResolvedAction`，Provider 只接收 `LLMRequest`，Workflow 與 UI 只接收既有 typed projection。最小且正確的介入點是：

```text
Canonical Feature Skeleton
          +
Validated Action Language Pack
          │
          ▼
ActionLanguagePackCompiler
          │
          ▼
既有 ConfigBundle / ActionCatalog / OutputProfileCatalog
          │
          ▼
既有 Runtime、Workflow、Provider、UI consumer
```

Phase 1 應建立一個可替換、可驗證、整包原子的 **Action Language Pack** 機制。Runtime 在 process 啟動後只持有一份已編譯 catalog，不持有 locale decision，也不支援 hot swap。

### 1.2 為什麼是 Yellow

現況不是 Red，因為：

- `app/config_loader.py` 已是單一 config loading seam。
- `ActionCatalog.resolve()` 已集中 base／variant 合成。
- `PromptBuilder` 與 `ResultProcessor` 已共用同一 `OutputProfileCatalog`。
- Provider、Workflow、Voice Input、TTS 不依賴 locale。

現況也不是 Green，因為：

- `ActionDefinition` 同時承載不可翻譯行為與可替換文字。
- Prompt placeholder 直到 Action 執行時才驗證。
- Output Profile 的人類文字 marker 沒有 stable semantic ID。
- 啟動時任一 config 損壞只會終止，沒有 selected-pack fallback。
- Action version 沒有完整包含 name、profile resources 與 pack provenance。

因此應先建立一個 bounded intervention，再增加第二個語言包；不可直接複製整份 `actions.yaml`。

---

## 2. 已確認的產品決策

以下決策已由使用者逐輪確認，實作者不得自行改回其他方向。

### 2.1 Phase 1 納入範圍

語言包提供：

- 全域 default system prompt。
- Action 與 explicit variant 的 `name`。
- Action 與 explicit variant 的 `system_prompt`、`prompt`。
- Feedback 的 `helps`、`does_not` 與 reason label。
- Output Profile 的 `instruction`。
- 透過 stable semantic marker ID 對應的人類可讀 marker literal。

### 2.2 Phase 1 明確不納入

- `config/entry_panel.yaml` 的 category／candidate 文案。
- Tray、Popup、Provider Settings、Shortcut Guide 框架等 UI 文案。
- `contextual_question`／`voice_draft_follow_up` 的合成 Action 名稱與 system prompt。
- Voice Input language。
- TTS voice 或 Speech Speed。
- 通用 Action output-language preference。
- 使用者匯入、下載、第三方或任意資料夾 discovery。
- process 內 hot reload／catalog hot swap。
- 自動重啟。
- 不完整語言包的欄位級或 Action 級 fallback。
- 預先設計尚無 consumer contract 的 `ui_resources`／`workflow_resources`。

### 2.3 等價原則

Pack locale 不決定 Action output language。固定目標 Action 的語意不變：例如 `translate_to_traditional_chinese` 在 `ja-JP` pack 中仍然翻譯成繁體中文；保留來源語言的 Action 仍然保留來源語言。

`zh-TW` pack 必須逐字重建目前 effective prompt、feedback 與 profile 行為。建立語言包時不得順便清理、改寫或最佳化 prompt。

---

## 3. Repo 調查證據

### 3.1 已驗證事實

| 事實 | 權威位置 | 影響 |
| --- | --- | --- |
| 27 個 Action | `config/actions.yaml` | Pack 必須 exact coverage |
| 6 個 explicit long variant | `config/actions.yaml` | 必須比較 explicit topology，不能只看 resolve 結果 |
| 30 個 Shortcut，其中 27 個 `start_action`、3 個非 Action | `config/shortcuts.yaml` | Shortcut 只屬骨架，pack 只能宣告相容 |
| 10 個 effective Output Profile | `config/output_profiles.yaml` | 必須在 `plain_text` 自動補值前比對 raw inventory |
| 現有所有 Action／variant prompt 只使用一次 `{input}` | `config/actions.yaml` | Phase 1 template contract 可 fail closed |
| 任一 config `ConfigError` 目前使 startup error + exit 2 | `main.py` | 必須新增 selected-pack fallback bootstrap |
| `UserPreferencesCoordinator` 在 bundle 載入後才建立 | `app/container.py` | Pack selection 需要獨立、較早的 bootstrap owner |
| Tray callback 已透過 typed command queue | `ui/tray.py`、`app/container.py` | Pack 選擇必須沿用相同 intent 路徑 |
| `PromptBuilder` 到執行時才 `.format(input=...)` | `services/prompt_builder.py` | Placeholder 錯誤目前太晚 |
| Follow-up 會再次直接 format Action prompt | `services/follow_up_continuation.py` | Compile-time validation 必須同時保護初始與 Follow-up |
| Profile instruction 同時供 request 與 result processing | `services/prompt_builder.py`、`services/result_processor.py` | 不可建立第二套 profile owner |
| Presentation parser 消費固定控制 token | `services/presentation.py` | `[[SCROLL_BREAK]]` 等不可翻譯 |
| Voice Input language 已有獨立 preference | `services/voice_input.py`、`platform/user_preferences.py` | 不可重用成主語言 |
| TTS 依實際文字 script 選 voice | `services/speech_coordinator.py` | 不得讀取 pack locale |

### 3.2 觀察與推論分離

已觀察：後段執行鏈已經只依賴已解析的 Action／Profile catalog。
推論：只要 compiler 在啟動前組回相同 catalog，後段不需要語言分支。

已觀察：`config/entry_panel.yaml` 有獨立繁中文案。
推論：Phase 1 會存在日文 Action title 與繁中 Entry Panel 並存；這是已接受的 scope，不得宣稱 UI 已完整在地化。

已觀察：現有 config 文件稱 `config/` 為使用者設定，但 repo 沒有承諾任意自訂 Action／Prompt 的 runtime migration contract。
推論：Phase 1 採一次性 canonical migration，不建立 legacy dual loader；若未來要支援自訂 pack，另立產品與安全規格。

---

## 4. 必須保護的既有行為

任何里程碑都不得改變：

- Action ID、Shortcut ID、hotkey、short／long press 語意。
- 6 個 explicit long variant 的存在與繼承關係。
- input mode、external fallback、output mode、stream、temperature。
- Personal Style mode 與 binding 時機。
- Action → Output Profile reference。
- Profile presentation mode。
- Feedback reason ID、順序與 inheritance topology。
- Selection-first、clipboard fallback、image input 與 canonical content 規則。
- Workflow admission、Foreground Workflow、provider binding、cancellation 與 late completion 規則。
- Follow-up bounded history 與 root-specific policy。
- Provider request contract；`LLMRequest` 不新增 locale。
- Voice Input language、TTS voice、Speech Speed 的 owner 與生命週期。
- 一個 process 只有一份 active `ActionCatalog` 與 `OutputProfileCatalog`。

`zh-TW` migration 完成時，下列內容必須與 migration 前逐字或逐欄位相等：

- app default system prompt。
- 每個 base／resolved variant 的 name、system prompt、prompt、feedback。
- 每個 profile instruction 與 required marker literal。
- 每個 resolved Action 的功能欄位。
- Shortcut matrix。

---

## 5. Progressive architecture diagnosis

### 5.1 Single owner

| 狀態／規則 | 唯一 owner |
| --- | --- |
| 功能骨架與 topology | canonical skeleton config + skeleton loader |
| Pack schema、parity、template 與 marker 驗證 | `ActionLanguagePackCompiler` |
| Config I/O、manifest path、checksum、YAML parse | app-layer pack loader adapter |
| active／selected／pending／restart／recovery 狀態 | `ActionLanguagePackSelectionCoordinator` |
| selection persistence | `ActionLanguagePackSelectionStore` adapter |
| bootstrap fallback | app-layer bootstrap module，完成後把 state 移交 coordinator |
| Runtime Action resolution | 既有 `ActionCatalog` |
| reusable output format | 既有 `OutputProfileCatalog` |
| Tray 呈現 | `TrayController` adapter，只投影、不擁有決策 |

### 5.2 Reusable capability or exception

這是 reusable capability：未來每個官方 Action language pack 都經相同 manifest、compiler、selection lifecycle 與 release gate。不得為 `ja-JP` 寫專屬 Python 分支。

### 5.3 Boundary leakage

必須阻止以下知識外洩：

- Pack path／manifest 不得進入 services、Provider 或 UI。
- Locale 不得進入 Workflow policy、`ActionInvocation` 或 `LLMRequest`。
- Pack 不得提供 shortcut、behavior field、presentation mode 或控制 token。
- Tray 不得讀 config、驗證 checksum 或寫 selection file。
- Selection store 不得解析 pack 或決定 fallback。

### 5.4 Enforceable safeguard

- Strict schemas：未知欄位、未來版本、重複 key fail closed。
- Contract hash：精確綁定 skeleton。
- AST architecture tests：禁止錯層 import 與 locale branch knowledge。
- Cross-pack structural golden matrix。
- `zh-TW` baseline digest fixture。
- CI pack validator：每個 registry pack 都必須通過。
- Release checklist：`ja-JP` 需要母語審查記錄才能加入 registry。

### 5.5 Debt multiplier

若直接複製整份 `actions.yaml`，新增三個語言後會產生至少四份行為設定 owner；每次 Action、variant、shortcut、feedback、profile 或 placeholder 變更都要跨四份同步。漏改一份仍可能通過現有局部 schema，直到特定語言的特定 Action 被執行才失敗。這會放大：

- configuration drift；
- hidden runtime failure；
- review ambiguity；
- profile／Action 雙重格式 owner；
- feedback 資料不可追溯；
- 變更與測試成本近似按語言數成長。

---

## 6. Target architecture

### 6.1 Deep modules 與 seams

依 codebase-design vocabulary，本方案只新增兩個主要深 module。

#### Module A：`ActionLanguagePackCompiler`

Interface：

```python
compile_pack(
    skeleton: FeatureSkeleton,
    manifest: ActionLanguagePackManifest,
    resources: ActionLanguageResources,
) -> CompiledActionLanguagePack
```

Interface invariants：

- input 已完成 UTF-8 decode 與 YAML typed parse；不包含 filesystem path。
- 成功回傳的 compiled pack 一定是 exact、完整、可 render 的 immutable 結果。
- 任一 mismatch 只回傳 typed validation error；不產生部分 catalog。
- caller 不需知道 Action／variant／profile 的逐欄位驗證順序。

Implementation 隱藏：inventory parity、feedback inheritance、Prompt parser、marker resolution、canonical contract hash、profile reference、version context 與 effective catalog composition。

Deletion test：若刪除此 module，所有 parity 與 composition 規則會散落到 loader、bootstrap、Tray selection 與 CI；因此它具有足夠 depth。

#### Module B：`ActionLanguagePackSelectionCoordinator`

Interface：

```python
state -> ActionLanguagePackSelectionState
begin_select(pack_id: str, operation_id: str) -> SelectionUpdate
execute(work: SelectionWork) -> SelectionOutcome
complete(operation_id: str, outcome: SelectionOutcome) -> SelectionUpdate
```

Interface invariants：

- 一次只有一個 selection operation。
- `execute` 必須先完整 validate，再 atomic save。
- save 成功前不改 `selected_pack_id`。
- `active_pack_id` 在 process 生命週期內不變。
- stale work／completion 不得改變 projection。
- 成功選擇只改變 next-start selection 與 `restart_required`。

Implementation 隱藏：pending gate、validate-before-save ordering、rollback、recovery visibility 與 stale identity checks。

#### Adapters

- app pack loader adapter：讀 registry／manifest／payload、驗 checksum、呼叫 compiler。
- platform JSON selection store adapter：atomic load/save。
- app runtime adapter：TaskSupervisor 排程與 typed completion routing。
- Tray adapter：radio／label projection 與 typed intent。
- test adapters：in-memory pack backend 與 selection store。

這些 adapters 不應各自形成一個只有單一 pass-through method 的公開 module；能保持 private 的 I/O helper 應留在 app loader implementation 內。

### 6.2 Layer placement

```text
clipai/core/
  models.py                         # 跨層 identity/state/provenance
  commands.py                       # typed select/completed intent
  ports.py                          # selection store / validation backend seam

clipai/services/
  action_language_packs.py          # compiler + pure validation/composition
  action_language_selection.py      # selection lifecycle owner

clipai/app/
  language_pack_loader.py           # registry/manifest/payload I/O adapter
  language_pack_bootstrap.py        # startup resolution + fallback
  runtime_action_language.py        # command routing / background execution
  config_loader.py                  # 載入 skeleton，再接收 compiled resources
  config_schema.py                  # bundle identity/schema projection
  container.py                      # assembly only
  runtime.py                        # typed dispatch only

clipai/platform/
  action_language_selection.py      # atomic JSON selection store

clipai/ui/
  tray.py                           # projection only
```

若實作後 `services/action_language_packs.py` 需要 import `app`、`platform`、`ui` 或 `providers`，視為架構失敗。

### 6.3 Bootstrap data flow

```text
main.py
  │
  ▼
bootstrap_application_configuration()
  ├─ load registry
  ├─ load canonical skeleton + shortcuts
  ├─ compute feature contract
  ├─ load selected pack ID
  ├─ validate every registry pack
  ├─ resolve selected/default fallback
  ├─ compile active pack into existing catalogs
  └─ return BootstrappedConfiguration
       ├─ ConfigBundle
       └─ ActionLanguagePackBootstrapState
  │
  ▼
build_runtime(bundle, bootstrap_state)
```

`main.py` 只呼叫 bootstrap interface；不得自己解析 manifest 或實作 fallback。

### 6.4 Runtime selection data flow

```text
Tray select pack
  → SelectActionLanguagePack(pack_id, operation_id)
  → RuntimeActionLanguageModule
  → coordinator.begin_select()
  → pending projection；舊 radio selection 保持可辨識
  → TaskSupervisor maintenance worker
  → coordinator.execute()
       1. 重新讀取並完整驗證 candidate
       2. 成功後才 atomic save selected ID
  → ActionLanguagePackSelectionCompleted
  → coordinator.complete()
  → Tray projection：active 不變，selected 更新，restart_required=True
```

不呼叫 `ReloadConfiguration`，不替換 `ActionCatalog`，不影響既有 Workflow。

---

## 7. Configuration design

### 7.1 建議目錄

```text
config/
  config.yaml                       # 非語言 app/provider/runtime/TTS 設定；移除 system_prompt
  actions.yaml                      # canonical Action skeleton
  output_profiles.yaml              # canonical profile skeleton
  shortcuts.yaml                    # 保持唯一 shortcut owner
  entry_panel.yaml                  # Phase 1 不變
  language_packs.yaml               # official registry + default
  language_packs/
    zh-TW/
      manifest.yaml
      app.yaml
      actions.yaml
      output_profiles.yaml
    ja-JP/
      manifest.yaml
      app.yaml
      actions.yaml
      output_profiles.yaml
```

`ja-JP` 在完成母語審查前可以存在 repo，但不得列入 `language_packs.yaml`。

### 7.2 Official registry

```yaml
schema_version: 1
default_pack_id: zh-TW
packs:
  - pack_id: zh-TW
    path: language_packs/zh-TW
  - pack_id: ja-JP
    path: language_packs/ja-JP
```

規則：

- registry order 是 Tray 顯示順序，屬 UX 行為，納入測試。
- default 只由 registry 指定；pack manifest 不可自稱 default。
- path 必須是 `config/` 下的 relative path。
- 禁止 absolute path、`..`、symlink escape 與重複 pack ID。
- 不掃描未列入 registry 的資料夾。

### 7.3 Manifest

```yaml
schema_version: 1
pack_id: ja-JP
locale: ja-JP
display_name: 日本語
pack_version: 1.0.0
feature_contract_hash: sha256:<canonical-hash>
resources:
  app:
    path: app.yaml
    sha256: <raw-file-sha256>
  actions:
    path: actions.yaml
    sha256: <raw-file-sha256>
  output_profiles:
    path: output_profiles.yaml
    sha256: <raw-file-sha256>
```

Manifest 規則：

- `schema_version` 必填，不支援 legacy v0。
- `pack_version` 必須是 SemVer，不接受 range。
- `pack_id` 必須與 registry entry 及目錄 identity 相符。
- resource path 必須停留在 pack root。
- checksum 在 YAML parse 前驗證 raw bytes。
- checksum 的目的在偵測錯配／損壞；Phase 1 官方內建包不宣稱以 checksum 防止惡意竄改。
- unknown field fail closed。
- manifest 不預留 `ui_resources` 或 `workflow_resources`。

### 7.4 Canonical Action skeleton

保留 `config/actions.yaml` 作為 Action 功能骨架的單一來源，schema bump 後不再包含可替換文字。

概念範例：

```yaml
schema_version: 11
actions:
  - id: translate_to_english
    input_mode: selection_or_clipboard
    external_fallback: selection_or_clipboard
    output_mode: popup
    output_profile: plain_text
    stream: true
    temperature: 0.2
    prompt_variables: [input]
    feedback_reason_ids:
      - meaning_changed
      - tone_changed
      - wording_unnatural
      - important_detail_missing
      - other
    press_variants:
      long:
        output_profile: plain_text
        prompt_variables: [input]
        feedback_reason_ids:
          - meaning_changed
          - relationship_or_register_wrong
          - wording_unnatural
          - important_detail_missing
          - other
```

Skeleton 規則：

- Action ID、Action order、behavior fields 與 explicit variant topology 只有此處可改。
- variant 只有 explicit override 才出現。
- feedback inheritance 必須由 schema 明確表示；不可由 pack 自行省略後猜測。
- `prompt_variables` Phase 1 必須精確為一次 `input`。
- pack schema 根本不接受 behavior fields。

### 7.5 Canonical Output Profile skeleton

```yaml
schema_version: 2
profiles:
  - id: reading_friction_practice
    presentation: markdown_sections
    markers:
      - marker_id: transfer_heading
        kind: localized
      - marker_id: scroll_break
        kind: control_token
        literal: "[[SCROLL_BREAK]]"
      - marker_id: hint_prefix
        kind: localized
```

規則：

- `id`、`presentation`、marker order、marker kind 屬骨架。
- `control_token.literal` 屬骨架，pack 不得提供或覆寫。
- `localized` marker 必須由 pack 以相同 `marker_id` 提供非空 literal。
- compiler 依 skeleton order 產生既有 `required_markers` tuple。
- `plain_text` 必須明確存在於 raw skeleton；不得依靠 `OutputProfileCatalog` 自動補值掩蓋缺漏。

### 7.6 Pack resources

`app.yaml`：

```yaml
schema_version: 1
default_system_prompt: |
  ...
```

`actions.yaml`：

```yaml
schema_version: 1
actions:
  translate_to_english:
    name: 英文翻譯
    system_prompt: |
      ...
    prompt: |
      ... {input} ...
    feedback:
      helps: ...
      does_not: ...
      reasons:
        meaning_changed: ...
        tone_changed: ...
        wording_unnatural: ...
        important_detail_missing: ...
        other: ...
    variants:
      long:
        name: 日文翻譯
        system_prompt: |
          ...
        prompt: |
          ... {input} ...
        feedback:
          ...
```

`output_profiles.yaml`：

```yaml
schema_version: 1
profiles:
  reading_friction_practice:
    instruction: |
      ...
    markers:
      transfer_heading: "## 換一句"
      hint_prefix: "卡住時再看："
```

Pack resource 規則：

- mapping key 使用 stable ID；duplicate YAML key fail closed。
- Action／variant／feedback reason／profile／localized marker ID 必須 exact match。
- pack 不可提供 control token、presentation、shortcut 或 behavior field。
- 空字串只允許 canonical contract 明確允許的欄位，例如 `plain_text.instruction`。
- base feedback 與 variant feedback 是否存在，由 skeleton 決定。

---

## 8. Validation and canonicalization

### 8.1 驗證順序

Compiler／loader 必須依下列順序 fail closed，錯誤需帶安全的 field path 與 error code：

1. Resolve registry path，拒絕 escape。
2. 讀 manifest，驗 UTF-8、大小上限、duplicate key、schema、unknown field。
3. Resolve resource path，拒絕 escape。
4. 讀 raw bytes，驗 SHA-256，再 decode／parse。
5. 驗 resource schema 與 unknown field。
6. 驗 manifest `feature_contract_hash` 等於目前 skeleton contract。
7. 驗 exact Action ID inventory。
8. 驗 explicit variant inventory 與 inheritance topology。
9. 驗 feedback reason ID 與 order。
10. 驗 exact Profile 與 localized marker inventory。
11. 驗 Prompt template contract。
12. 依 skeleton 合成 typed Action／Profile models。
13. 執行 cross-reference 驗證。
14. 對每個 base／explicit variant 做 sentinel render smoke。
15. 建立 complete version context 與 immutable compiled result。

任一步失敗都不得回傳部分 catalog或保存 selection。

### 8.2 Prompt template contract

使用 `string.Formatter().parse()`，Phase 1 規則：

- 每個 Action／explicit variant prompt 必須剛好包含一次 `{input}`。
- field name 只能是 `input`。
- 禁止 positional field、attribute traversal、index traversal。
- 禁止 conversion，例如 `!r`。
- 禁止 format spec，例如 `:>10`。
- unmatched braces fail closed。
- system prompt、default system prompt、profile instruction 不做 template interpolation；若出現保留 placeholder 語法，應視為可疑並由明確 validation rule 拒絕或要求 escape。
- render smoke 使用包含 braces、非 ASCII 與換行的 sentinel，驗證初始 Action 與 Follow-up 重建都不會失敗。

不要在 `PromptBuilder` 或 `FollowUpContinuation` 各維護一套 allowlist。Runtime 可保留 defensive error handling，但權威規則只在 compiler。

### 8.3 Feature contract hash

建立 deterministic canonical JSON，再以 UTF-8 SHA-256 計算：

- schema／contract version。
- Action ID exact inventory。
- explicit variant topology。
- 所有不可翻譯 Action behavior fields。
- prompt variable occurrence contract。
- feedback reason ID 與順序。
- Shortcut ID、normalized hotkey、command、Action reference及顯示順序。
- Profile ID、presentation、marker ID／kind／order。
- control token literal。
- Action／variant → Profile reference。

Canonicalization 規則必須本身有測試：

- 不具語意的 mapping key order 不影響 hash。
- 會影響 UX／行為的 sequence order 必須影響 hash。
- whitespace 只在 YAML parse 後的 typed value 層正規化；Prompt 本文不可 trim 或改行尾後再拿來組 catalog。
- hash algorithm／prefix 固定為 `sha256:`。

### 8.4 Action version and provenance

擴充 Action version input，使其包含：

- 現有 resolved Action version payload。
- resolved Action／variant name。
- effective Output Profile instruction、required markers、presentation。
- pack ID、pack version、locale。
- pack resource content hash 或等價的 version salt。

建議讓 `ActionCatalog` 接收 immutable `ActionVersionContext`，因為 `ActionCatalog` 已是 Action version 的 owner；不要在 Workflow、Feedback store 或 UI 重算 hash。

`ResolvedAction`／`WorkflowStep` 應攜帶 typed pack provenance，`ActionFeedbackRecord` 新增：

- `action_language_pack_id`
- `action_language_pack_version`
- `action_language_locale`

Feedback reason 仍只保存 stable reason ID，不保存語言化 label。Diagnostics 只記 pack identity、contract hash、safe error code，不記 Prompt 全文。

---

## 9. Selection state and fallback

### 9.1 Typed state

```python
@dataclass(frozen=True)
class ActionLanguagePackSelectionState:
    available_packs: tuple[ActionLanguagePackDescriptor, ...]
    active_pack: ActionLanguagePackIdentity
    selected_pack_id: str
    pending_pack_id: str | None = None
    operation_id: str = ""
    restart_required: bool = False
    recovery: ActionLanguagePackRecovery | None = None
    message: str = ""
```

語意：

- `active_pack`：本 process 真正編譯進 catalog 的 identity，process 內 immutable。
- `selected_pack_id`：已成功保存、下次啟動要嘗試的 ID。
- `pending_pack_id`：正在重新驗證／保存的候選。
- `restart_required`：selected 與 active 不同。
- `recovery`：startup 因 selected invalid 而採 default 的 typed reason。

`ActionLanguagePackRecovery` 至少攜帶 `requested_pack_id`、typed reason 與安全 diagnostics code；不得依賴壞 manifest 的 display name 才能呈現 recovery truth。

不可用 Workflow revision、provider operation ID 或 generic preference revision 代替 selection operation identity。

### 9.2 Persistence

檔案：`data/action_language_pack.json`

```json
{
  "schema_version": 1,
  "selected_pack_id": "ja-JP"
}
```

Store 規則：

- tempfile 與目標檔位於同目錄。
- `flush()`、`os.fsync()`、`os.replace()`。
- finally 清 temp。
- missing file → default ID。
- corrupt／future schema → default ID + safe diagnostic；不把壞 payload 傳入 Runtime。
- store 只保存 ID，不保存 locale、version 或 path。
- 不與 `user_preferences.json` 共用 aggregate或 operation gate。

### 9.3 Startup algorithm

```text
load registry + skeleton
validate every registry pack
  ├─ default invalid → ConfigError / startup error / no Runtime
  ├─ non-default invalid → omit from available + safe diagnostic
  └─ valid → available map

load persisted selected ID
  ├─ selected valid → active = selected
  └─ selected missing/invalid/incompatible
       → active = default
       → selected 仍保留原 ID
       → recovery = typed reason

compose active pack into ConfigBundle
```

不得因某個 selected Action resource 失敗而混入 default 的對應欄位。

### 9.4 Tray projection

建議 menu label：

- 正常：`Action Language（目前：繁體中文）`
- 已保存待重啟：`Action Language（目前：繁體中文；重啟後：日本語）`
- recovery：`Action Language（所選語言不可用；目前：繁體中文）`

行為：

- radio check 表示 `selected_pack_id`，不是假裝已 active。
- 若 persisted selected pack 已失效而不在 `available_packs`，Tray 需額外呈現一個 disabled、checked 的 `requested_pack_id（不可用）` recovery item；不可把 default 誤畫成使用者已重新選擇。
- pending 時保留原 selected check，disable所有 pack option。
- 保存成功後才改 check。
- validation／save failure 保持舊 selected，顯示真實 failure。
- recovery warning 持續可見，不跳 Popup、不發 system notification。
- 使用者成功選回 active default 並保存後，可清除可見 recovery；diagnostic event 仍保留。

---

## 10. Failure taxonomy

不要用訊息字串反推 failure。至少定義：

| Error code | 條件 | 選擇時 | 啟動時 |
| --- | --- | --- | --- |
| `registry_invalid` | registry schema/path/duplicate 錯誤 | 不應可選 | default 無法解析則 fatal |
| `pack_missing` | registry path／manifest 不存在 | 不保存 | selected fallback；default fatal |
| `manifest_invalid` | schema／unknown field／SemVer 錯誤 | 不保存 | selected fallback；default fatal |
| `resource_path_invalid` | absolute／escape／missing | 不保存 | selected fallback；default fatal |
| `checksum_mismatch` | raw bytes hash 不符 | 不保存 | selected fallback；default fatal |
| `contract_mismatch` | feature hash 不同 | 不保存 | selected fallback；default fatal |
| `inventory_mismatch` | Action／variant／profile 多或少 | 不保存 | selected fallback；default fatal |
| `feedback_contract_mismatch` | reason ID／order／inheritance drift | 不保存 | selected fallback；default fatal |
| `prompt_template_invalid` | placeholder／brace／format rule 錯誤 | 不保存 | selected fallback；default fatal |
| `marker_contract_mismatch` | marker ID／kind／control token 錯誤 | 不保存 | selected fallback；default fatal |
| `selection_save_failed` | atomic persistence 失敗 | 保持舊 selected | 不適用 |

User-facing message 可以語言化於目前 UI 語言，但 typed code 必須穩定且 diagnostics 不包含 prompt 原文。

---

## 11. Implementation milestones and tiny commits

每個 commit 都應能獨立 review；不得先刪除舊 config 再於後續 commit 修復啟動。

### M0 — Freeze baseline

建議 commit：`test: freeze action language baseline`

變更：

- 新增 `tests/fixtures/action_language/zh_tw_baseline_hashes.json`。
- 記錄 migration 前：default system prompt、每個 resolved Action／variant文字與結構、profile instruction／markers、Shortcut matrix 的 deterministic digest。
- 新增測試證明目前所有 prompt 只有一次 `{input}`。
- 新增測試證明 27 Action、6 explicit long variant、30 Shortcut、10 profile。

完成條件：baseline test 在未改 config 前通過；fixture 不複製成第二份可編輯 prompt owner。

### M1 — Define skeleton and pack contracts

建議 commit：`feat: define action language pack contracts`

變更：

- 在 core 新增必要 identity、descriptor、provenance、selection state 與 typed errors。
- 在 `services/action_language_packs.py` 建立 pure compiler interface。
- 定義 skeleton、manifest、resource typed models。
- 實作 exact inventory、Prompt、feedback、marker 與 contract hash 驗證。
- 新增 table-driven unit tests，全部經 compiler public interface。

完成條件：valid in-memory pack 可編譯；所有 mismatch 都是 typed failure；services 不碰 filesystem。

### M2 — Add app loader and official registry

建議 commit：`feat: load verified action language packs`

變更：

- 新增 `app/language_pack_loader.py`。
- 實作 registry／manifest／resource path containment、checksum、UTF-8、strict YAML parse。
- 加入 in-memory／tmp-path tests。
- 新增 `scripts/validate_language_packs.py`，供 CI／release 使用同一 loader／compiler，不複製驗證規則。

完成條件：CLI 與 app loader 對同一壞包回相同 typed error code。

### M3 — Split canonical config and create byte-identical `zh-TW`

建議拆成兩個 commit：

1. `refactor: split action skeleton from language resources`
2. `test: prove zh-TW language pack parity`

變更：

- `config/actions.yaml` 只保留 skeleton。
- `config/output_profiles.yaml` 只保留 profile skeleton／marker role／control token。
- `config/config.yaml` 移除 default system prompt。
- 建立 `config/language_packs/zh-TW/*`。
- 更新 `config_loader.py` 以 compiled pack 組成既有 catalog。
- 更新所有直接呼叫 `load_action_catalog("config/actions.yaml")` 的測試／scripts，統一經新權威 loader fixture。
- 不保留舊格式 runtime loader。

完成條件：M0 所有 baseline digest 完全相同；既有 runtime/provider/UI tests 無需增加 locale fixture。

### M4 — Complete action version and feedback provenance

建議 commit：`feat: record action language provenance`

變更：

- `ActionCatalog` 接收 immutable version context。
- version hash 納入 pack identity、name 與 effective profile content。
- `ResolvedAction`、`WorkflowStep`、`ActionFeedbackRecord` 帶 typed provenance。
- 更新 append-only feedback record schema；舊 record 讀取／分析若有 consumer，需提供明確 backward read policy，不改寫舊檔。

完成條件：只改 pack version、name 或 profile instruction 都會得到新的 action version；不同語言 feedback 可按 pack identity 分辨。

### M5 — Bootstrap fallback

建議 commit：`feat: bootstrap action language fallback`

變更：

- 新增 atomic selection store adapter。
- 新增 `app/language_pack_bootstrap.py`。
- `main.py` 改呼叫單一 bootstrap interface。
- 回傳 `ConfigBundle + bootstrap state`。
- selected invalid 回退 default；default invalid 使用既有 startup error surface。
- 非 selected invalid pack 從 available list 移除。

完成條件：fallback 不產生部分 catalog、不改寫 selection、不建立第二個 Runtime。

### M6 — Runtime selection lifecycle

建議拆成兩個 commit：

1. `feat: coordinate action language selection`
2. `feat: expose action language selection in tray`

變更：

- 新增 core typed command／completion。
- 新增 selection coordinator 與 tests。
- 新增 app runtime module，透過 maintenance worker 執行 validation／save。
- `AppRuntime` 只 dispatch typed command。
- `container.py` 組裝 coordinator、store、loader backend 與 Tray callbacks。
- Tray 顯示 active／selected／pending／restart／recovery。

完成條件：成功保存前不改 radio；active catalog process 內不變；stale completion 無效。

### M7 — Add and review `ja-JP`

建議拆成：

1. `feat: add Japanese action language pack candidate`
2. `test: verify Japanese action semantic parity`
3. `feat: release Japanese action language pack`

步驟：

- 先建立 pack，但不加入 registry。
- 執行 machine validator 與 cross-pack matrix。
- 由日文母語審查者檢查全部 Action／variant／feedback／profile。
- 對固定目標語言 Action 特別確認沒有隨 pack locale 改變 target。
- 紀錄 review artifact／版本。
- 最後一個 commit 才加入 official registry。

完成條件：registry 中的 `ja-JP` 已通過全部 release gate，而不是「先顯示、之後再補翻譯」。

### M8 — Architecture docs and release hardening

建議 commit：`docs: codify action language pack ownership`

變更：

- 更新 `docs/ARCHITECTURE_BOUNDARIES.md`。
- 更新 `docs/TESTING_STRATEGY.md`。
- 更新 stale 的 `docs/contracts/services/config-readiness-contract.md` schema 敘述。
- 新增 Action Language Pack contract／ADR，或將本文件中的 ADR 落成正式檔案。
- 更新 `docs/RELEASE_CHECKLIST.md`。
- 新增 architecture tests。

完成條件：正確路徑最容易，錯層 import／locale branch／未驗 pack 能被 CI 偵測。

---

## 12. File-by-file change map

| 檔案 | 預期變更 | 不得做的事 |
| --- | --- | --- |
| `main.py` | 呼叫 bootstrap interface、沿用 startup error | 不解析 manifest、不自行 fallback |
| `app/config_loader.py` | 載 skeleton、接 compiled resources | 不掃 pack 目錄、不保存 selection |
| `app/config_schema.py` | 加 active pack identity／schema metadata | 不加 UI locale master field |
| `app/language_pack_loader.py` | I/O、checksum、strict parse、compiler adapter | 不持有 selection lifecycle |
| `app/language_pack_bootstrap.py` | startup resolve/fallback | 不做 runtime hot swap |
| `app/runtime_action_language.py` | typed command + worker + completion | 不重建 active catalogs |
| `app/container.py` | assembly | 不放 validation policy |
| `app/runtime.py` | dispatch | 不用 pack ID 字串特判 Workflow |
| `core/models.py` | identity/state/provenance | 不放 YAML/path 邏輯 |
| `core/commands.py` | select/completed typed intents | 不放 UI callback |
| `core/ports.py` | store/backend seams | 不暴露 config loader implementation |
| `services/action_language_packs.py` | deep compiler | 不讀 filesystem |
| `services/action_language_selection.py` | single state owner | 不 import app/platform/ui |
| `services/action_catalog.py` | complete version context | 不選 locale |
| `services/prompt_builder.py` | 接既有 compiled text；保留 defensive error | 不讀 pack |
| `services/result_processor.py` | 使用 compiled profile | 不翻譯 marker |
| `services/follow_up_continuation.py` | 不需 locale change | Phase 1 不搬 synthetic resources |
| `platform/action_language_selection.py` | atomic JSON store | 不驗 pack、不決定 fallback |
| `ui/tray.py` | projection + intent | 不讀 config/store/manifest |
| `config/entry_panel.yaml` | Phase 1 不變 | 不偷偷併入 Action pack |

---

## 13. Test plan

### 13.1 Compiler interface tests

至少涵蓋：

- valid `zh-TW`／`ja-JP` in-memory pack。
- manifest future／missing schema。
- duplicate key、unknown field、invalid SemVer。
- pack ID／locale／registry mismatch。
- missing／extra Action。
- missing／extra explicit variant。
- base／variant feedback inheritance mismatch。
- feedback reason missing／extra／reordered。
- missing／extra profile。
- pack 嘗試提供 presentation／control token／behavior field。
- localized marker missing／extra。
- `{inputs}`、missing `{input}`、double `{input}`、bad brace。
- `input.foo`、`input[x]`、`!r`、format spec。
- Action reference unknown profile。
- deterministic contract hash。
- success result 沒有 partial／optional catalog。

### 13.2 Loader adapter tests

- resource SHA mismatch。
- absolute path、`..`、resolved escape。
- missing manifest／payload。
- invalid UTF-8。
- registry duplicate／default missing。
- non-selected bad pack 被 omit。
- same error code in validator CLI and loader。

### 13.3 Baseline and cross-pack tests

對全部 27 Action × `short`／`long` resolution：

- ID、press type、input/output policy、fallback、temperature、stream 相同。
- explicit variant topology 相同。
- output profile ID／presentation 相同。
- feedback reason ID／order相同。
- Prompt variable contract 相同。
- Shortcut matrix完全相同。
- `zh-TW` effective text digest 與 migration 前相同。
- 只有允許的語言 resource 欄位可跨 pack 不同。

### 13.4 Selection coordinator tests

- validation 成功後才 save。
- validation failure 不呼叫 save。
- save failure 保持舊 selected。
- pending 保持 active／selected truth。
- single-flight gate。
- duplicate selection ignored。
- stale work／completion ignored。
- successful selection sets restart required but not active。
- successful reselect active default clears visible recovery。

### 13.5 Bootstrap tests

- missing selection file → default。
- selected valid → selected active。
- selected missing／corrupt／incompatible → default active + recovery，selection 不改寫。
- default invalid → startup error，Runtime 未建立。
- non-selected invalid → app starts，pack omitted。
- selection file corrupt／future schema → default + diagnostic。
- fallback 不混用任何 selected resource。

### 13.6 Tray tests

- menu order 等於 registry order。
- checked state 等於 persisted selected。
- label 同時呈現 active／next-start。
- pending disable options且不 optimistic check。
- validation/save failure 顯示失敗並維持舊值。
- recovery warning 持續可見。
- Tray callback 只 enqueue typed command。

### 13.7 Provenance tests

- pack version、name、prompt、feedback、profile instruction／marker任一改變會改 action version。
- Feedback record 保存 stable reason ID + pack identity。
- diagnostics 不含 Prompt 全文、input 或 output。

### 13.8 Architecture tests

新增 AST 規則：

- Provider、WorkflowController、Voice Input、Speech/TTS 不得 import pack modules。
- UI 不得 import config loader、selection store、filesystem path 或 YAML。
- services pack module 不得 import app/platform/ui/providers。
- `LLMRequest`、`ActionInvocation` 不新增 locale／pack decision field；provenance metadata不得改變 execution policy。
- 只有 app composition 可同時知道 skeleton loader、pack loader 與 concrete store。
- 禁止 `if locale ==`／`if pack_id ==` 進入 Runtime execution、Provider 或 UI widget；Tray display mapping只能使用 descriptor projection。
- 不得保留 legacy language-aware Action loader與新 compiler並行。

### 13.9 Manual smoke

在互動式 Windows desktop 驗證：

1. `zh-TW` 啟動，抽測 short／long Action、feedback、profile marker。
2. Tray 選 `ja-JP`，看到 pending → saved → restart required。
3. 重啟前執行 Action，仍使用 `zh-TW`。
4. 重啟後使用 `ja-JP`，hotkey、Workflow、Provider、Voice Input、TTS 沒有被切換。
5. 人工破壞 selected `ja-JP` checksum，重啟後使用 `zh-TW` 並看到 Tray recovery。
6. 修復包但不改 selection，下一次重啟重新嘗試並可成功使用。
7. 破壞 default pack，確認 startup fail closed。

---

## 14. Verification commands

依風險由小到大執行；實際 test filename 可依最終命名調整，但不得跳過測試類別。

```powershell
& .\.venv\Scripts\python.exe -m pytest tests\services\test_action_language_packs.py
& .\.venv\Scripts\python.exe -m pytest tests\app\test_language_pack_loader.py tests\app\test_language_pack_bootstrap.py
& .\.venv\Scripts\python.exe -m pytest tests\services\test_action_language_selection.py tests\platform\test_action_language_selection_store.py tests\ui\test_tray.py
& .\.venv\Scripts\python.exe -m pytest tests\app\test_config.py tests\services\test_session_and_action.py tests\services\test_follow_up_continuation.py
& .\.venv\Scripts\python.exe -m pytest tests\architecture
& .\.venv\Scripts\python.exe -m compileall ClipAI scripts tests
& .\.venv\Scripts\python.exe scripts\validate_language_packs.py
& .\.venv\Scripts\python.exe scripts\run_unit_tests.py
```

最後依 `docs/TESTING_STRATEGY.md` 執行對應 Windows manual smoke。此功能不需要真實 provider 才能驗證 config、selection 與 fallback；日文語意品質評估才使用代表性 provider run。

---

## 15. Release gates

### 15.1 Machine gate

- 所有 registry pack schema、checksum、contract hash通過。
- exact inventory與 Prompt render smoke通過。
- architecture tests通過。
- full unit suite通過。
- packaged/source launcher都能找到同一官方 registry與 pack path。

### 15.2 Behavior parity gate

- `zh-TW` baseline digest 100% 相同。
- 全 Action／variant／Shortcut／Profile structural matrix相同。
- 固定 target-language Action 沒有因 pack locale 改變 target。
- Voice Input、TTS、UI locale欄位沒有被 pack selection寫入。

### 15.3 Native-language gate

日文母語審查逐項確認：

- Action task semantics。
- Human Space 的「AI 幫你／AI 不做什麼」。
- Feedback reasons 與 stable ID 的語意對應。
- 安全、忠實度、不確定性與不代替人判斷的限制。
- Profile structure、localized marker與控制 token。
- Popup title不與第一個 output heading重複。
- 英文學習 Action 對日文使用者的說明自然，但沒有改變學習任務。

審查完成前 `ja-JP` 不得列入 official registry。

---

## 16. Migration and rollback

### 16.1 Reversible migration

- M0 先建立 baseline，提供所有後續 rollback判斷依據。
- M1／M2 只新增 compiler／loader，不改 active path。
- M3 在同一組可 review commits中切換 active path並證明 `zh-TW` parity。
- M5 後才導入 fallback；M6 後才暴露 Tray selection。
- `ja-JP` 最後才進 registry。

### 16.2 Rollback strategy

在正式 release 前，任何 milestone可透過 revert cohesive commit回復，不使用 runtime feature flag維持兩套 owner。

正式 release後若 `ja-JP` 有內容問題：

- 從下一版 official registry移除 `ja-JP`，保留 pack檔供診斷／修復。
- 已選 `ja-JP` 的使用者會依既定 selected-invalid policy回退 `zh-TW`，selection不自動改寫。
- 不修改 Workflow／Provider做緊急語言特判。

若 compiler／bootstrap本身有缺陷，回退整個語言包 release；不要重新啟用 legacy dual loader。

---

## 17. Options considered

| 選項 | 好處 | 成本／風險 | 可逆性 | 判斷 |
| --- | --- | --- | --- | --- |
| 暫時接受現況，複製完整 config | 最快看到日文 | 行為 drift、晚期錯誤、多 owner | 低 | 拒絕 |
| Local refactor，只抽 prompt 檔 | 改動較小 | 無法驗 Shortcut／variant／profile／feedback parity | 中 | 不足 |
| **Incremental migration：skeleton + strict pack compiler** | 小 seam、完整驗證、Runtime不變 | 增加 loader／schema／測試成本 | 高 | **採用** |
| Core rebuild／通用 i18n framework | 可一次涵蓋全部 UI | 高風險、超出需求、引入大量語言分支 | 低 | 拒絕 |

---

## 18. Concise ADR

### Context

ClipAI 需要讓日文與未來語言使用者取得功能一致的 Action content，同時維持 Action ID、Shortcut、Workflow、Provider、UI lifecycle與安全規則不變。現行 config混合功能行為與可替換文字，且缺少整包相容驗證與 fallback。

### Decision

建立官方、完整、restart-only 的 Action Language Pack。Canonical skeleton保留所有不可翻譯行為；strict compiler驗證 manifest、checksum、exact inventory、Prompt變數、feedback與profile marker後，於 app config composition seam組回既有 catalogs。Selection使用獨立原子 store與 coordinator；selected壞包回退 `zh-TW`，default壞包 fail closed。

### Alternatives rejected

- 每個語言複製完整 Action config。
- partial fallback。
- Runtime／Provider／UI locale branch。
- 共用 Voice Input language作主語言。
- process內 hot swap。
- Phase 1全面 UI i18n。

### Consequences

正面：功能骨架單一、錯誤提前、語言包可驗證、Feedback可追溯、後段 Runtime穩定。
負面：新增 manifest／compiler／selection／release gate；每個正式包需要完整資源與母語審查。

### Review triggers

只有出現下列情況才重新評估：

- 產品正式要求可安裝第三方 pack。
- UI locale出現第一個獨立 consumer contract。
- 合成 Workflow prompt需要正式語言資源 owner。
- generic Action output-language preference有明確產品需求。
- pack數量使啟動時完整驗證產生可量測的延遲。
- skeleton需要支援除 `{input}` 外的新變數。

---

## 19. Definition of Done

全部條件同時成立才算完成：

- 只有一份 canonical feature skeleton。
- `zh-TW` 與 release後的 `ja-JP` 都是完整、valid official pack。
- `zh-TW` effective behavior與 migration前一致。
- Action／variant／Shortcut／Profile／feedback／placeholder drift會在啟動或選擇前被拒絕。
- validation失敗不保存選擇。
- selection成功只在重啟後生效。
- selected損壞回退 default且不改寫 selection。
- default損壞 fail closed。
- Runtime、Workflow、Provider、Voice Input、TTS沒有 locale branch。
- Feedback與diagnostics可追溯 pack identity且不洩漏prompt／內容。
- Tray反映真實 active／selected／pending／restart／recovery lifecycle。
- 所有 targeted、architecture、unit與manual smoke通過。
- `ja-JP` 有可稽核的母語審查記錄。
- 架構文件、contract、release checklist與實作同步。

---

## 20. Remaining uncertainty

目前沒有阻塞實作的產品決策。仍需由實作者在 M0 以測試確認的唯一高價值事實是：

- 目前每個 explicit variant 的 feedback override／inheritance exact topology。
- 每個 profile marker中哪些是 parser control token、哪些是 localized literal。
- source launcher與未來 packaged distribution對 `config/` relative path的實際定位方式。

這些都是 repo事實，不需要再向產品詢問。若發現與本文件盤點不同，先更新 baseline evidence與contract，不可用特判繞過。
