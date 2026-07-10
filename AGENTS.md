# ClipAI agent contract

開始任何修改前，必須完整閱讀：

- `docs/Product_philosophy.md`
- `docs/ARCHITECTURE_BOUNDARIES.md`
- `docs/TESTING_STRATEGY.md`

任何文件缺失或彼此衝突時，停止修改並回報，不可自行猜測架構。

## 工作流程

1. 先執行 `git status --short`，辨識並保留使用者既有變更。
2. 將工作拆成可獨立驗證、可回退的 cohesive changes。
3. Contract 改變時，同一個 commit 更新對應 tests 與架構文件。
4. 驗證順序為 targeted tests、architecture tests、完整 unit suite、必要的 integration smoke test。
5. 刪除舊碼前用 `rg` 搜尋 imports、tests、config、scripts 與 docs；替代品驗證後立即刪除，不保留無期限 compatibility shim。

## 不可違反的架構規則

- `core` 只能依賴 Python standard library。
- `services` 只能依賴 `core`。
- `platform`、`providers`、`ui` 只能依賴 `core` 或 standard library/第三方套件。
- 只有 `app` 可以組裝 concrete services、platform、providers 與 UI。
- 主流程使用直接 method call；跨 thread 使用 typed command queue；禁止 global Event Bus。
- 每個 session 只有一個 `SessionController` 可以改變狀態。
- Provider worker 不得直接更新 Tkinter；UI 更新只能回到主 thread。
- 設定在啟動時解析成 typed immutable models，不得用 raw dict 穿越 layers。
- 不得把業務決策放進 `support`、generic utility、UI 或 provider adapter。

## Commit 規則

- Agent 應依變更責任自行拆 commit，不使用固定行數判斷大小。
- 一個 commit 只回答一個問題；implementation 與其 tests 放在同一 commit。
- 不混入格式化、無關 cleanup、其他 phase 或使用者既有變更。
- commit 前檢查 `git diff --cached`；每個 commit 必須可理解、可回退並通過該 slice 的 gate。
- 使用 `docs:`、`test:`、`refactor:`、`feat:`、`fix:` 等清楚前綴。
- 若 baseline 已失敗，先記錄既有失敗，不得加入新的失敗。
