# 「問這段」V1 契約

## 產品目的

「問這段」讓使用者先指定 AI 應閱讀的外部文字，再以鍵盤或既有 Voice
Input 提出自己的問題。它不是 Action，也不會在問題送出前呼叫 provider。

使用者心智模型只有兩個入口：

- `Ctrl+Alt+R`：指定要問的內容。
- `Ctrl+Alt+W`：對目前 ClipAI 問題欄說話；沒有 ClipAI 問題欄時，維持既有
  Voice Draft 行為。

## 使用流程

1. 使用者反白文字，或準備純文字剪貼簿。
2. 按 `Ctrl+Alt+R`。
3. ClipAI 在 intent 當下擷取 selection；selection 無文字時改讀 clipboard
   text。圖片不屬於 V1。
4. Popup 標題顯示「問這段」，header 以既有 source preview 顯示來源前幾個
   字元，並自動聚焦既有 Follow-up composer，placeholder 為「想知道什麼？」。
5. 使用者可打字，或按住 `Ctrl+Alt+W` 將辨識文字插入 composer。語音完成
   不會自動送出。
6. 空白問題不可送出。按 Enter 或 Send 後才建立第一次 provider invocation，
   request 由固定 source snapshot 與 question 組成。
7. 回答完成後，同一個 composer 回到既有 Follow-up 生命週期。

若聚焦的 ClipAI result Popup 已存在，`Ctrl+Alt+R` 只開啟該 Workflow 的
composer，不擷取新來源、不建立新 Workflow、也不呼叫 provider。

## 資料與失敗規則

- source snapshot 在 `Ctrl+Alt+R` 當下固定；之後的 clipboard、selection 或
  foreground window 變化都不會改寫它。
- source 與 question 只存在目前 Workflow 記憶體；關閉後丟棄，不寫入偏好、
  歷史、log 或 diagnostics。
- selection 與 clipboard fallback 必須重用 container-scoped
  `ClipboardTransactionCoordinator` 所提供的既有 input seam。
- 無文字時清楚失敗並關閉暫存 Workflow；不建立 provider invocation。
- source 超過 40,000 字元時不截斷，要求使用者縮小選取範圍。
- AI 以 source 為主要證據；一般知識只用於解釋術語或背景。source 缺少答案
  所需事實時，必須明說，不得補造。

## 架構決策（ADR）

### Context

一般 Action 在觸發後立刻組 prompt 並呼叫 provider；既有 Follow-up 則要求已有
completed Workflow step。「問這段」位於兩者之間：它先固定來源，等待使用者
提出第一次問題。

### Decision

- 新增 `OpenContextualQuestion` 與 `SubmitContextualQuestion` typed intents。
- `WorkflowController` 是 contextual source snapshot、capture identity、question
  composer request 與後續 step history 的唯一 owner。
- `WorkflowRuntimeModule` 只負責 Workflow admission、非 provider capture 排程與
  provider binding。
- 初次提問和後續提問共用 `FollowUpContinuation` 的深層 interface；contextual
  root 在 implementation 內隔離 source data、問題與 bounded history。
- `contextual_question` 是內部 step semantic identity，不進入 Action catalog，
  不套用 Action feedback contract 或 YAML prompt。

### Alternatives

- 新增 YAML Action：拒絕，因為它會在使用者尚未提問時先做一次低價值 API
  呼叫，且混淆 source 與 question。
- 讓 `Ctrl+Alt+W` 依外部 caret 自動推測 intent：拒絕，Windows 無法提供跨
  應用程式穩定且普遍的 editable-caret 判斷。
- 建立第二套問答 session/controller：拒絕，會複製 Workflow state ownership。

### Consequences and review trigger

V1 多一個明確快捷鍵，但 Voice Input gesture 不變，且不需 caret heuristic。
若未來出現第二個需要「固定多個 inputs、等待補齊後再送出」的功能，再檢討是否
把 contextual source draft 提升為一般 multi-input Workflow contract；在那之前
不建立推測性的 multi-input Action framework。
