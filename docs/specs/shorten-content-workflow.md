# Shorten Content Workflow Spec

## Goal

讓使用者以 `Ctrl+Alt+X` 將外部文字或目前 displayed Workflow result 連續縮短，保持核心語意並維持同一 visible Workflow。

## Behavior

- Short press：目標輸出約為原內容的 20%，保留原意、事實、語氣、名稱、數字與限制。
- Long press：刪除所有非必要文字，輸出仍可理解的最短表達。
- 有有效 Workflow context 時，Workflow surface selection 優先，否則使用 displayed successful result。
- 無有效 Workflow context 時，selection-first、clipboard fallback。
- Chained result 顯示於同一 visible Workflow surface，可用 Back 返回上一個成功 step。
- Processing 保留舊內容；failure 不破壞舊結果或 history。

## Acceptance

- `Ctrl+Alt+X` short/long resolve 至同一 action 的正確 variant。
- Workflow chaining 不建立第二個 Workflow/window。
- 多個 pinned Workflow 中，只有 runtime 認定的 Foreground Workflow 可提供 context。
- 被取代 invocation 的 late completion 不覆蓋目前 result。
- Existing external-only Actions 不因 visible Workflow 存在而改變 input source。
