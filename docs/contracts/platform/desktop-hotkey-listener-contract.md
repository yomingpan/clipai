# Platform Desktop Hotkey Listener Contract

## Intent

Desktop hotkey listener 的核心意圖是讓使用者能快速啟動已定義的 shortcut，同時穩定區分 short press 與 long press。

這個 contract 是人類意圖、架構邊界、使用者可見行為與測試案例之間的中介層。它的目標不是增加文件量，而是讓 AI coding context 可以穩定理解：`clipai/platform/hotkey.py` 只負責把真實 OS 鍵盤事件轉成可預測、可測試、可注入上層流程的 trigger。

品質標準是使用者可預測性。使用者按了什麼，系統就只能根據那個實際操作觸發對應結果；如果 OS 事件混亂、modifier 殘留或 release 順序異常，hotkey listener 必須優先避免誤觸。

## Boundary

`clipai/platform/hotkey.py` 屬於 `platform/`，是 desktop OS keyboard listener 的接縫。

它可以做：

- 讀取 shortcut map 裡的 `id` 與 `hotkey` 欄位。
- 將 hotkey 字串 canonicalize 成可比對的 token set。
- 監聽 OS key press / release events。
- normalize top-row digits、numpad digits、letters 與 modifier keys。
- 區分 short press 與 long press。
- 透過 callback 回報 `shortcut_id` 與 `press_type`。

它不可以做：

- 決定 prompt。
- 呼叫 provider。
- 開啟 popup。
- 寫入 clipboard。
- 決定使用者是否應該看到某個結果。
- 解讀 action variant 的產品語意。
- 主動驅動 action pipeline。

依賴方向必須符合 `docs/ARCHITECTURE_BOUNDARIES.md`：`platform` 可依賴 `core` contract 或共用型別，但不得依賴 `ui` 或 `provider`，也不應把業務流程決策放進 platform。

## Definitions

### Shortcut

在這份 contract 中，`shortcut` 是 shortcuts config 中已定義的 binding，核心識別是 `id`。

Hotkey listener 不「選擇」業務行為。它只在註冊時把某個 hotkey token set 綁定到 `shortcut_id`，並在觸發時回報該 `shortcut_id`；上層 `ShortcutCatalog` 才解析 typed command。

### Press Type

`press_type` 只能是：

- `short`：一般短按，代表一般執行。
- `long`：按住超過 long press threshold 的長按事件。

目前 long press threshold 是 `500ms`，對應 `LONG_PRESS_SEC = 0.5`。

Long press 的實際產品行為由上層 runtime、services 或 action variant 決定。Hotkey listener 不知道也不應知道 long press 會使用哪個 prompt、model、provider、output mode 或 UI 行為。

### Modifier Mode

`modifier_mode` 是相容設定。

它只負責把舊或不同 modifier 前綴 canonicalize 成目前模式，降低 hotkey 遷移破壞。例如既有 `alt+shift+1` 可依設定轉成 canonical hotkey。`modifier_mode` 不代表 hotkey listener 可以決定產品行為。

## Inputs / Outputs

### Inputs

- `shortcut_map`：由上層傳入的 shortcut definitions mapping。
- `hotkey` string：每個 shortcut definition 中的 hotkey 設定。
- OS key press / release events：由 desktop keyboard listener 提供。
- `modifier_mode`：hotkey modifier prefix 的相容 canonicalization 設定。
- `long_press_sec`：short / long press 的時間閾值。

### Output

唯一業務輸出是：

```python
on_trigger(shortcut_id, press_type)
```

其中：

- `shortcut_id` 是 shortcut definition 的 `id`。
- `press_type` 只能是 `short` 或 `long`。

## Behavior Guarantees

Hotkey listener 必須保證：

- Short press 只觸發一次 `short`。
- Long press 觸發 `long` 後，release 時不得再觸發 `short`。
- 多個 shortcut hotkey 彼此隔離，不得互相污染 active state。
- Modifier key 順序改變時仍能穩定比對。
- Top-row digits、numpad digits 與 letters 必須穩定 normalize。
- Shifted digit characters，例如 `!`、`@`、`#`，應回到對應 digit。
- 無法 normalize 的 key event 不應觸發 action。
- Listener stop 後不得留下會繼續觸發 action 的 listener。

## User Trust Red Lines

誤觸是 hotkey listener 的最高風險。

特別是 modifier 殘留狀態，例如 OS 或 listener 認為 `alt` 還按著，但使用者其實已經放開。這類狀態如果造成 action 被觸發，會直接破壞使用者信任。

當 OS 鍵盤事件混亂時，優先順序是：

1. 避免誤觸。
2. 避免殘留 pressed state 造成不可預測行為。
3. 維持使用者對按鍵行為的可預測性。
4. 再考慮避免漏觸。

不能為了猜測使用者意圖而觸發 action。沒有足夠可信的 key state 時，寧可不觸發，也不能觸發錯誤 action。

## Forbidden Decisions

`clipai/platform/hotkey.py` 不得做以下決策：

- 選擇 action prompt。
- 解析 long press 對應哪個 prompt 或 provider。
- 呼叫任何 LLM provider。
- 開啟或更新 popup。
- 寫入 clipboard。
- 決定 output mode。
- 決定使用者看到的結果。
- 決定是否 archive、speak、copy 或 follow up。
- 根據 action 內容改變 key matching 行為。

這些決策屬於 config、app composition、runtime、services 或 UI，不屬於 platform hotkey。

## Testing Links

已存在測試：`tests/platform/test_hotkey.py`

目前覆蓋：

- `expand_hotkeys` 使用 `ctrl+alt` 作為 canonical default。
- legacy `alt+shift` 可依 `modifier_mode` rewrite 成 `ctrl+alt`。
- `ctrl+shift` 在指定模式下保持穩定。
- top-row digits 使用 vk fallback normalize。
- numpad digits 使用 vk fallback normalize。
- letters 使用 vk fallback normalize。
- short press 只觸發 short。
- long press 不在 release 時再觸發 short。
- 多個 shortcut hotkey 彼此隔離。

應補 unit / sims 測試：

- 重複 press 不造成重複 timer 或多次觸發。
- 重複 release 不造成多次觸發。
- modifier release 順序改變仍能清理 active state。
- shifted digit characters 正確 normalize。
- 無法 normalize 的 key event 不觸發 action。
- 快速連按同一 hotkey 不殘留 pressed 或 active state。
- timer fire 與 release 接近同時發生時不觸發 short + long 雙重事件。
- listener stop 後呼叫底層 listener stop，且 `running` 狀態變成 false。

## Manual / Integration Scenarios

這些情境應在真實 app 啟動後手動或以 integration test 驗證；不要求每項在本 contract 建立時立刻自動化。

- 真實 listener 可註冊與釋放。
- app stop 後 listener 被確實停止。
- 快速連按同一 hotkey 不殘留狀態。
- 快速切換兩個不同 shortcut hotkey 不互相污染。
- 先按 modifier 再按 digit、先按 digit 再放 modifier，都不造成誤觸。
- top-row digit 與 numpad digit 行為一致。
- 長按超過 `500ms` 只觸發 long，不觸發 short。
- 短按低於 `500ms` 只觸發 short，不觸發 long。
- OS focus 切換或 modifier key 異常 release 後，不得因殘留狀態觸發 action。

## Trigger release timing

- A short Shortcut dispatches as soon as all of its non-modifier trigger keys
  are released. Ctrl, Alt, or Shift may remain physically held.
- Releasing a modifier first ends long-press timing but does not dispatch the
  pending Shortcut until its non-modifier trigger keys are released.
- A fired long press emits `long_release` when its non-modifier trigger keys
  are released. Later modifier releases must not emit duplicate events.
- Held speech composition follows the same rule: releasing the selected Action
  key dispatches its speech-routed command without waiting for Q or modifiers.

## Stale physical-key recovery

- The listener reconciles every normalized pressed token against the physical
  Windows key state before matching a new non-injected key-down event.
- Only tokens explicitly reported as released are stale. An unavailable or
  unsupported physical-state query returns unknown and preserves the token.
- Recovery removes stale tokens and cancels only active timers or pending
  releases whose Shortcut bindings contain those tokens.
- The key-down event that reveals stale state continues through normal matching,
  so a fresh Shortcut chord works on its first attempt.
- When recovery occurred and the revealing key does not match a Shortcut, the
  listener does not emit an additional `invalid` trigger.
- Top-row and numpad digits share normalized tokens. Either physical key keeps
  that token active.
- Tests must cover a missed ordinary-key release followed by a held speech
  composition sequence and assert that no unrelated popup Action is emitted.

## Decision Log

- 2026-07-26: Changed pending Shortcut dispatch from all-chord release to
  non-modifier trigger-key release for immediate user feedback.
- 2026-07-26: Generalized stale-state recovery from modifiers to every supported
  normalized hotkey token. The platform listener remains the single owner of
  physical keyboard reconciliation.

- 2026-06-07：建立 platform desktop hotkey listener contract。
- Hotkey listener 的核心意圖是快速啟動 action，且穩定區分 short / long press。
- Hotkey listener 只輸出 `shortcut_id + press_type`。
- Short press 是一般執行。
- Long press 是超過 `500ms` 的長按事件。
- Long press 的產品語意由上層 runtime/services/action variant 決定。
- `modifier_mode` 是相容設定，不是產品行為決策入口。
- 避免誤觸與殘留 modifier state 優先於猜測使用者意圖。
- Contract 需同時作為規範文件與 AI coding context，並隨測試與行為演進持續更新。
