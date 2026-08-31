# Action Language Pack × Unified Entry Panel 架構評估與執行規劃

> 狀態：已於 2026-08-31 依本規劃完成實作；本文件保留實作前決策與邊界
> 評估基準：`codex/action-language-packs` @ `1304c2c`，已 rebase 至 `develop` @ `c72f784`
> 架構分類：**Yellow**
> 主要建議：**在既有 Language Pack compiler／config composition seam 做可逆的增量遷移**
> 信心：高

> 實作驗證：official validator 通過 2 packs；compileall 通過；unit／architecture suite `1072 passed, 10 deselected`。10 個需真實 OS／UI 的 integration tests 未在本輪自動執行。

## 0. 文件目的與範圍

本文件規劃讓 Unified Entry Panel 的 **Action 候選文案** 跟隨目前 active Action Language Pack：使用者選擇 `ja-JP` 並重啟後，Recent、scene flagship、More 與搜尋結果中的 Action `label`、`description` 應顯示日文；`zh-TW` 必須維持目前繁中文案。

本次採以下明確邊界：

- 納入：Entry Panel candidate 的 `label`、`description`，以 `action_id + press_type` 為 stable identity。
- 納入：Recent、flagship、advanced／More 與搜尋所使用的同一份 candidate presentation。
- 不納入：category 的 `label`、`description`、Panel 標題、搜尋框、More、密度切換、pending/error/disabled reason 等 UI chrome。
- 不納入：全域 UI locale、Workflow、Provider、Voice Input、TTS、execution policy 或 process 內 hot swap。
- 生命週期維持 restart-only；Tray 儲存 selection 後，現行 process 的 Panel 文案不可提前切換。

這個範圍把「Action 語言」延伸到 Action launcher 的呈現，但不把 Action Language Pack 偷換成整個應用程式的 locale framework。若產品期待 category 與 Panel chrome 也同步日文化，應在實作前另開 UI locale 決策，不應把它們混入本次 candidate resource。

---

## 1. Executive judgment

### 1.1 結論

目前 active pack 已正確決定 Action name、prompt、feedback 與 profile，但 Entry Panel 又從固定的 `config/entry_panel.yaml` 讀取繁中 candidate `label/description`。這形成同一個 Action presentation 的第二個語言 owner。

建議新增一個 **受限的 `entry_panel` pack resource**：canonical `config/entry_panel.yaml` 只保留 Panel IA、category copy 與 `action_id + press_type` membership；每個 official pack 完整提供候選 Action 文案。既有 pure compiler 驗證 exact topology，app loader 驗證 manifest/checksum，`load_config_bundle()` 在啟動時一次組成 `EntryPanelCatalog`。Runtime、coordinator 與 UI 只消費已編譯 projection，不判斷 locale。

```text
config/entry_panel.yaml
  category/slot/order/flagship/advanced + Action refs
                         +
active pack/entry_panel.yaml
  exact Action ref -> localized label/description
                         │
                         ▼
ActionLanguagePackCompiler
                         │ immutable, complete
                         ▼
load_config_bundle() -> EntryPanelCatalog
                         │
                         ▼
EntryPanelCoordinator -> typed snapshot -> UI
```

### 1.2 為什麼是 Yellow

不是 Red：既有 Language Pack bootstrap、compiler、fallback、restart-only selection 與 Entry Panel catalog/coordinator 邊界都已存在，不需要重寫 Runtime。

不是 Green：若只在 `config/entry_panel.yaml` 再加日文欄位、由 UI 看 locale 分支，或直接以 Action name 覆蓋 label，會新增 workaround、破壞 baseline 或留下兩套 owner。應先完成 bounded contract migration，再加入日文文案。

---

## 2. Triggering evidence

### 2.1 已驗證事實

| 事實 | 證據 | 影響 |
| --- | --- | --- |
| 原始 Action Language Pack 計畫明確排除 Entry Panel category/candidate copy | `docs/specs/action-language-pack-development-plan.md` §2.2、§3.2 | 本需求是已完成機制的有界 scope extension，不應改寫原歷史計畫 |
| active pack 已在建立 `ActionCatalog` 前解析 | `clipai/app/config_loader.py:49-60` | 正確 seam 已存在 |
| Entry Panel 隨後固定讀取 `config/entry_panel.yaml` | `clipai/app/config_loader.py:61`、`clipai/app/language_pack_bootstrap.py:39,97` | `ja-JP` active 時仍會載入繁中 candidate copy |
| Panel candidate 自己保存 `label/description` | `clipai/services/entry_panel.py:9-13` | Action presentation 有第二個 owner |
| Recent、scene、More、search 都使用 candidate copy | `clipai/services/entry_panel.py:115-185,318-337` | 修正 catalog composition 即可覆蓋全部入口，不需 UI 分支 |
| `config/entry_panel.yaml` 有 27 個 candidate | repo inventory check | pack 必須 exact coverage，不可 partial fallback |
| 27 個 candidate 中有 10 個繁中 label 不等於 resolved Action name | repo inventory comparison | 直接改用 `ActionCatalog.resolve().name` 會改變既有繁中 UX；label 不是可安全推導值 |
| manifest 目前只接受 `app/actions/output_profiles` 三個 resource | `clipai/app/language_pack_loader.py` manifest/resource parser | extension 必須是明確 schema/manifest 變更，不可旁路讀檔 |
| `EntryPanelCoordinator` 與 UI 不讀 pack identity | `clipai/services/entry_panel.py`、`clipai/ui/unified_entry_panel.py` | 可保持 locale-free consumer |
| Entry Panel tests 已固定 IA/order，Language Pack tests已固定 baseline/topology/fallback | `tests/app/test_entry_panel_config.py`、`tests/app/test_action_language_baseline.py`、`tests/app/test_official_action_language_packs.py` | 新驗證應加在既有 gates，而不是另建平行測試機制 |
| branch 在評估開始時無未提交檔案 | `git status --short` | 本文件是本輪唯一變更 |

### 2.2 觀察與推論分離

已觀察：Panel 文案是在 app composition 階段建立，之後只作 immutable projection。
推論：只要 bootstrap 組出 active-pack-aware `EntryPanelCatalog`，Runtime 不需要新增 locale state 或 reload path。

已觀察：10 個 candidate label 是 Action name 的刻意簡化或改寫。
推論：label/description 是 surface-specific Action presentation，不應從 executable Action definition 動態猜測。

已觀察：Language Pack 已採整包驗證、selected invalid 全包 fallback。
推論：Entry Panel Action copy 必須成為同一個 pack 的 required resource；欄位級 fallback 會破壞現有原子性。

---

## 3. Current capability and protected behavior

實作必須保護：

- `action_id + press_type`、category ID、slot、順序、flagship/advanced membership 不變。
- Recent 仍只保存 Action reference，不保存 localized string；重啟後以當次 active pack 重新投影。
- 搜尋仍比對目前 projection 的 label/description/action ID；日文 pack 下自然可用日文字串搜尋。
- `EntryPanelCoordinator` 仍擁有 navigation/search/density/disabled projection。
- `EntryPanelRuntimeModule` 仍擁有 Panel lifecycle、source 與 selection-preparation identity。
- `WorkflowRuntimeModule.start_action` 仍是唯一 Action admission seam。
- `ActionCatalog` 仍擁有 execution definition；Panel resource 不得提供 prompt、input/output mode、provider、Personal Style 或 availability。
- `zh-TW` 的 27 組 candidate label/description 逐欄位不變。
- default pack 任一 required resource 無效時 startup fail closed；selected non-default 無效時完整 fallback `zh-TW`，不可混包。
- selection 成功只改 next-start pack；目前 process 的 `EntryPanelCatalog` 與 Action catalogs 保持 active pack 一致。

---

## 4. Four-part architecture diagnosis

### 4.1 Single ownership

| 狀態／規則 | 唯一 owner |
| --- | --- |
| Panel IA、category ID/slot/order、flagship/advanced membership | canonical `config/entry_panel.yaml` |
| category 與 Panel UI chrome copy | 既有 Entry Panel/UI config；本次不遷移 |
| candidate Action `label/description` | active Action Language Pack 的 required `entry_panel` resource |
| candidate inventory/topology 與文字完整性 | `services/action_language_packs.py` pure compiler |
| resource path、UTF-8、checksum、manifest schema | `app/language_pack_loader.py` |
| skeleton + localized copy 的組裝 | `app/config_loader.py` |
| navigation/search/recent projection | `EntryPanelCoordinator` |
| restart-only selection lifecycle | `ActionLanguageSelectionCoordinator` |
| widget rendering | `UnifiedEntryPanelDialog`，只呈現 snapshot |

### 4.2 Reusable capability or exception

這是 reusable capability。每個 official pack 都以相同 schema 提供完整 candidate presentation，未來新增語言不需要 Python branch、額外 config path 或 UI condition。不得為 `ja-JP` 寫專屬 loader。

### 4.3 Boundary propagation

允許跨界的只有 typed、immutable candidate presentation：

```text
pack filesystem -> app loader -> pure compiler -> app composition
-> EntryPanelCatalog -> EntryPanelSnapshot -> UI
```

不得傳播：

- pack path、manifest、checksum 到 `services/entry_panel.py` 或 UI；
- locale/pack ID 到 coordinator、Panel widget、Workflow、Provider 或 execution intent；
- raw localization dictionaries 跨 app/services boundary；
- category/UI chrome 字串進入本次 resource；
- candidate 文案反向成為 Action execution name、prompt 或 version policy。

### 4.4 Enforceable safeguards

- manifest 必須宣告 exact required resource set，新增 `entry_panel` checksum。
- compiler 以 `action_id + press_type` 驗證 missing、extra、duplicate、order/topology 與非空文字。
- `feature_contract_hash` 納入 canonical category/slot/order/flagship/advanced Action refs，但不納入任何 localized literal。
- `resource_content_hash` 納入 `entry_panel` resource，維持整包 provenance 與原子 fallback；不建立第二個 locale identity。
- `zh-TW` baseline fixture 納入所有 candidate label/description。
- cross-pack tests 比對 exact candidate ref topology。
- architecture test 禁止 UI、Workflow、Provider、Voice/TTS import pack owner 或依 pack ID 分支。
- official validator 驗證 registry 中每一包，不只 selected pack。

---

## 5. Debt multiplier

目前的 multiplier 是 **duplicated presentation ownership + configuration drift**。若維持現況並再增加三種語言，可能出現：

1. Action name/prompt 已翻譯，但 Panel label/description 仍繁中。
2. 每個語言在 UI 或 config loader 增加特例；Recent、scene、More、search 可能各走不同資料源。
3. 新增或移動 candidate 時，某些 pack 缺字串但仍通過 Action pack validator，直到使用者打開特定頁面才發現。

三次類似變更後，reviewer 必須同時理解 Action resource、Entry Panel config、UI branch 與 fallback precedence；測試成本按語言 × surface 增長，且無法證明 active Action 與 launcher copy 來自同一 pack。

---

## 6. Realistic options

| 選項 | 效益 | 成本／風險 | 可逆性 | 判定 |
| --- | --- | --- | --- | --- |
| A. candidate label 直接使用 resolved Action name，description 留在繁中 config | 幾乎不改 schema | 10/27 label baseline 改變；description 仍混語；surface-specific copy 消失 | 高 | 不採用 |
| B. official pack 新增受限 `entry_panel` candidate resource | exact coverage、保留 curated label、整包 fallback、未來 pack 可重用 | 需 schema/manifest/hash、兩包資源與測試 migration | 高 | **建議** |
| C. 建立全域 UI i18n／locale service | 可同時翻譯 category/chrome | scope 過大；新增 runtime locale owner，與 restart-only Action pack 混淆 | 中低 | 本次不採用 |

唯一主要建議是 B：局部、增量、可回退，且直接消除目前的 drift mechanism。

---

## 7. Recommended intervention

### 7.1 Configuration contract

將 canonical `config/entry_panel.yaml` schema bump，candidate 只保留：

```yaml
flagship:
  - action_id: explain_like_friend
    press_type: short
```

category 的 `id/slot/label/description` 與 candidate placement 仍留在此檔。禁止 candidate 再帶 `label/description`，避免 legacy owner 無限共存。

每個 pack 新增：

```text
config/language_packs/<pack-id>/entry_panel.yaml
```

建議 schema：

```yaml
schema_version: 1
candidates:
  - action_id: explain_like_friend
    press_type: short
    label: 友人のように説明
    description: 親しみやすく率直な言葉で内容を説明します。
```

規則：

- candidate identity 只能是 canonical skeleton 已列出的 `action_id + press_type`。
- exact coverage；不得缺漏、額外、重複或 partial fallback。
- `label/description` 必須是非空安全純文字；不得承載 template、Markdown control token 或 execution 欄位。
- 資源順序跟隨 canonical flattened order，compiler 回傳同序 immutable tuple。
- manifest required resources 由三項擴為四項：`app/actions/output_profiles/entry_panel`。
- 兩個 official pack 均 bump SemVer、重算 feature contract hash 與 raw-file checksum。

### 7.2 Typed compiler output

在既有 `services/action_language_packs.py` 內新增小型 immutable types，例如：

```python
EntryPanelCandidateSkeleton(action: EntryActionRef)
LocalizedEntryPanelCandidate(action: EntryActionRef, label: str, description: str)
```

並擴充：

- `FeatureSkeleton`：保存 canonical Entry Panel category/slot/ordered candidate topology。
- `ActionLanguageResources`：保存 localized Entry Panel candidate tuple。
- `CompiledActionLanguagePack`：提供已驗證的 candidate presentation tuple。

不要把 `EntryPanelCatalog` 或 navigation policy搬進 pack compiler。Compiler 只回答：「此 pack 是否完整提供 canonical candidate refs 的安全文案？」

### 7.3 Loader and composition

- `load_feature_skeleton()` 接受 `entry_panel_path`，由 app adapter 解析 IA topology，交 pure compiler 算 contract hash與驗證 exact coverage。
- `ActionLanguagePackLoader` 驗證第四個 resource 的 containment、UTF-8、schema、checksum，再傳 typed resources 給 compiler。
- `bootstrap_action_language_config()` 將同一個 `entry_panel_path` 同時交給 skeleton load 與 bundle composition。
- `load_entry_panel_catalog()` 解析 canonical category/placement，並以 compiled pack 的 typed presentation 做 exact join。
- `EntryPanelCatalog` 的公開介面、`EntryPanelCoordinator`、`EntryPanelRuntimeModule` 與 UI 不新增 locale/pack 參數。

### 7.4 Lifecycle truth

```text
process N: active zh-TW
  -> 使用者選 ja-JP
  -> validate 四個 resources + atomic save
  -> Tray 顯示 restart required
  -> Panel 仍使用 zh-TW catalog

process N+1:
  -> bootstrap selected ja-JP
  -> compile Action + Entry Panel resources as one pack
  -> build one ja-JP-aware EntryPanelCatalog
  -> Recent/scene/More/search 顯示日文 candidate copy
```

selected `ja-JP` 的 `entry_panel` resource 無效時，必須完整回退 default `zh-TW`：Action、prompt、feedback、profile 與 Panel candidate copy 全部來自同一包。不得使用日文 Action 搭配繁中 Panel fallback。

### 7.5 Exclusions

本次不得：

- 在 `UnifiedEntryPanelDialog` 判斷 locale 或讀 YAML；
- 在 coordinator 依 pack ID 切換字串；
- 新增 `ja-JP` Python branch；
- 讓 category/UI chrome 混進 Action candidate resource；
- 支援 hot reload 或替換已建立的 coordinator/catalog；
- 把 recent persistence 改成保存 label；
- 使用 Action name 作隱性 fallback；
- 保留 schema v1 candidate label 與 pack label 兩條長期有效路徑。

### 7.6 Observable completion criteria

- `ja-JP` active 且重啟後，27 個 candidate 的 label/description 全為審查過的日文；Recent、scene、More、search 使用同一份文案。
- `zh-TW` 的 27 組 candidate label/description 與目前版本完全相同。
- selection 存檔後、重啟前，Action 與 Panel 都維持舊 active pack。
- selected non-default 的第四資源 missing/checksum/schema/inventory 任一失敗時，整包 fallback `zh-TW` 並投影 recovery。
- default pack 第四資源無效時 fail closed。
- missing/extra/duplicate candidate ref 不能產生 partial catalog。
- UI、Workflow、Provider、Voice Input、TTS 無 pack import、locale field 或 pack identity branch。
- validator、targeted tests、architecture tests 與完整 unit suite 全綠。

---

## 8. Reversible migration sequence

每個步驟應是 cohesive commit，contract 與測試同步更新：

1. **Characterization gate**
   先將現有 27 組 `zh-TW` candidate label/description 加入 baseline fixture，新增 candidate inventory/topology characterization；此步不改 runtime behavior。
2. **Canonical topology contract**
   擴充 `FeatureSkeleton` 與 feature hash，讓 compiler 知道 Entry Panel ordered refs；先加入 pure failing tests。
3. **Pack resource compiler**
   加入 typed localized candidate models、exact validation、resource hash 與 compiled output；涵蓋 missing/extra/duplicate/empty/unknown ref。
4. **Filesystem loader**
   manifest required resources 加入 `entry_panel`，補 path/checksum/schema tests；新增兩個 pack resource 並重算 manifest/version/hash。
5. **Single composition path**
   schema bump canonical `config/entry_panel.yaml`，移除 candidate `label/description`，讓 `load_entry_panel_catalog()` 只從 compiled pack 接收 candidate copy。同一 commit 移除 legacy path，不留 indefinite dual ownership。
6. **Bootstrap/fallback/restart tests**
   驗證 active `ja-JP` bundle、invalid selected fallback、invalid default fail-closed，以及存檔後重啟前不變。
7. **Panel behavior verification**
   coordinator tests驗證 Recent/scene/More/search 的日文 projection；UI 僅驗證 Unicode snapshot rendering，不新增 locale logic。
8. **Docs and release gate**
   更新 ownership contract、architecture boundaries、testing strategy、release checklist、README/usage 與 `ja-JP` review record，明列 category/chrome 非本次 scope。

回退方式：整組 revert 本 extension commits 即可恢復 schema v1 的固定 candidate copy；直接 shortcuts、Workflow 與 Provider 完全不受影響。不要以同時保留兩個 reader 作 rollback 機制。

---

## 9. Verification plan

### 9.1 Pure compiler/service tests

- canonical category/slot/order/flagship/advanced ref topology 進入 feature hash。
- exact candidate coverage：missing、extra、duplicate、順序、unknown action、press type、空 label/description。
- `zh-TW`／`ja-JP` candidate refs 完全一致。
- resource content 變更會改 provenance hash；不改 execution behavior topology。
- `EntryPanelCoordinator` 的 Recent、scene、More、search 使用 injected localized candidate copy。

### 9.2 App/loader/bootstrap tests

- manifest 恰好四個 resources；缺少或多出 resource fail closed。
- checksum、path containment、UTF-8、schema、unknown field 全部覆蓋。
- `load_config_bundle(action_language_pack=ja_pack)` 產生日文 candidate catalog。
- default invalid fail closed；selected invalid 完整 fallback default；persisted selection 不被 fallback 改寫。
- `ActionLanguageSelectionCoordinator` 保持 restart-only，active catalog 不 hot swap。

### 9.3 Baseline and architecture gates

- baseline fixture bump，鎖住原 27 組繁中 candidate copy。
- official pack validator 驗證所有 registry packs。
- AST gate 禁止 UI/runtime execution owners import pack loader/compiler或依 `pack_id` 分支。
- Config tests繼續鎖住 PRD order、numeric slots、flagship limit、duplicate ref 與 fail-closed unknown fields。

### 9.4 Manual UI smoke

1. 以 `zh-TW` 啟動，檢查 Recent、四個 scene、More 與搜尋結果維持原繁中 Action 文案。
2. Tray 選 `ja-JP`，確認 pending/success/restart truth；不重啟重新開 Panel，文案仍為繁中。
3. 重啟，檢查相同位置的 candidate label/description 為日文，Action 執行仍使用相同 `action_id + press_type`。
4. 執行一個 Action 形成 Recent，重啟切換 pack，Recent reference 以新 active pack 重新顯示，store 仍只有 ID/press type。
5. 注入 invalid selected pack resource，確認 Action 與 Panel 一起回退繁中，無混包。

建議實作完成後執行：

```powershell
python scripts/validate_language_packs.py
python -m pytest tests/services/test_action_language_packs.py tests/services/test_entry_panel.py
python -m pytest tests/app/test_language_pack_loader.py tests/app/test_language_pack_bootstrap.py tests/app/test_official_action_language_packs.py tests/app/test_entry_panel_config.py tests/app/test_action_language_baseline.py
python -m pytest tests/architecture/test_action_language_boundaries.py
python scripts/run_unit_tests.py
```

真實 Windows/UI integration smoke 仍需在互動式桌面執行；unit green 不代表日文截斷、IME 搜尋或實際 widget spacing 已被驗證。

---

## 10. Concise ADR

### Context

Action Language Pack 已控制 executable Action 文字，但 Unified Entry Panel 以固定繁中 config 重複保存 Action candidate presentation，造成 active `ja-JP` 與 launcher copy 不一致。

### Decision

將 Entry Panel candidate `label/description` 納入 official Action Language Pack 的 required `entry_panel` resource。Canonical Entry Panel config 只擁有 IA、category copy 與 Action refs。既有 compiler 驗證 exact topology，loader 驗證 filesystem integrity，app composition 在 process start 建立單一 immutable catalog。所有 runtime/UI consumers 保持 locale-free，selection 維持 restart-only。

### Alternatives

- 由 resolved Action name 推導：拒絕，因現有 curated label 不等價且無法提供 description。
- UI 依 locale 分支：拒絕，會建立第二個 selection/string owner。
- 全域 UI i18n：延後，超出本次 Action-language scope。

### Consequences

- 優點：Active Action 與 Panel candidate copy 原子一致；新語言有 exact release gate；Recent 自動按 active pack 重投影。
- 成本：Entry Panel skeleton/manifest schema、pack SemVer、hash/checksum 與兩包內容需要同步 migration。
- 已接受後果：`resource_content_hash` 納入新 resource，因此只改 Panel candidate copy 也會改 pack provenance／Action version context；這維持 pack-level原子追溯，不另建第二個 provenance identity。

### Review triggers

- category 或 Panel chrome 也需要翻譯；
- process 內 hot swap；
- 第三方／使用者自訂 pack；
- 第二個非 Entry Panel consumer 需要同一套 launcher copy；
- entry-only copy 造成可量測的 Action-version analytics churn；
- pack 數量造成可量測 startup 延遲。

---

## 11. Uncertainty and highest-value next inspection

目前最大的非架構不確定性是 **日文 candidate copy 的語言品質**，不是資料流。實作前應先以現有 27 組繁中 label/description 產生日文候選稿，交由日文審查並把逐項結果加入 `docs/reviews/action-language-pack-ja-JP-review.md` 或獨立補充記錄。

本文件假設 category 與 Panel chrome 不屬本次「Action 語言」。若產品其實要求 `看得懂／寫得出／想清楚／工具` 及其描述也變日文，最高價值的下一步是先確認這個 scope；一旦納入，應規劃獨立的 Entry Panel locale resource 或 UI locale contract，而不是把 category 字串偽裝成 Action candidate。

除上述產品 scope 與日文審查外，沒有阻擋開始 M1 characterization tests 的技術問題。
