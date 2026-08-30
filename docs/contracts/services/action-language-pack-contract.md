# Action Language Pack Contract

Action Language Pack 只替換 Action 使用者可見文字與 prompt content，不是整個應用程式的 locale，也不改變 Action 行為。Phase 1 的 official packs 是 `zh-TW` 與 `ja-JP`。

## Authoritative owners

- `config/actions.yaml`、`config/shortcuts.yaml`、`config/output_profiles.yaml` 是唯一 canonical feature skeleton，擁有 Action ID、shortcut、input/output policy、variant topology、feedback reason ID、profile presentation 與 control token。
- `services/action_language_packs.py` 是 pure compiler，擁有 exact inventory、prompt variable、feedback topology、marker contract 與 deterministic provenance 的驗證規則；它不得讀 filesystem。
- `app/language_pack_loader.py` 是 official registry、path containment、UTF-8、schema 與 checksum 的 filesystem adapter。
- `app/language_pack_bootstrap.py` 是 process-start resolve owner。Default pack 無效時 fail closed；非 default pack 無效時 omit；selected pack 無效時完整回退 default，且不得混用兩包資源或改寫 persisted selection。
- `services/action_language_selection.py` 是 restart-only selection lifecycle 與 operation identity 的唯一 owner。`platform/action_language_selection.py` 只原子保存下一次啟動的 pack ID。
- `WorkflowController` 使用已編譯 catalog 並保存 provenance，但不選 pack、不解析 locale，也不重建 prompt。

## Lifecycle

```text
process start
  -> load canonical skeleton
  -> validate default and every registered pack
  -> resolve persisted selection or complete default fallback
  -> compile one immutable active catalog
  -> build Runtime

tray selection
  -> typed intent
  -> revalidate selected official pack
  -> atomically save next-start pack ID
  -> show restart required
```

Process 內不 hot swap。儲存新 selection 後，active catalog 在重啟前保持不變；這是 Tray 必須呈現的真實 lifecycle。

## Boundary rules

- Pack locale 不得成為 `LLMRequest` 或 `ActionInvocation` 的 execution-policy 欄位。
- Provider、Workflow execution、Voice Input 與 Speech/TTS 不得 import pack compiler、loader、bootstrap 或 selection modules。
- UI 只能呈現 `ActionLanguagePackSelectionState` 並 enqueue typed command；不得讀 YAML、registry、manifest、checksum 或 selection file。
- 固定目標語言 Action 的輸出語意不得跟 pack locale 改變。保留來源語言的 Action 也必須繼續保留來源語言。
- Pack 只能提供 manifest 中列出的完整資源。不得 partial fallback、目錄掃描、自訂第三方 pack 或語言專屬 Python branch。
- Feedback record 與 Action version 必須保存 pack identity、feature contract hash 與 resource content hash；diagnostics 不得保存 prompt、input 或 output。

## Release gate

新 official pack 必須通過 checksum/schema/compiler、cross-pack topology、固定輸出語意、baseline、architecture、full unit tests 與逐項語言審查。完成前可把 candidate 放進 repo，但不得加入 `config/language_packs.yaml`。

Review triggers：第三方 pack、process 內 hot swap、獨立 UI locale、skeleton 新增 `{input}` 以外變數、或 pack 數量造成可量測的啟動延遲。
