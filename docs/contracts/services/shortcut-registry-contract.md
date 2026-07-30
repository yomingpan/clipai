# Shortcut Registry Contract

## Intent

桌面快捷鍵綁定與業務功能定義必須分離。`ShortcutCatalog` 將
`ShortcutPressInvoked(shortcut_id, press_type)` 解析成 typed `AppCommand`；
listener 不理解 LLM、TTS 或 UI。

## Configuration

`config/shortcuts.yaml` 是唯一快捷鍵來源：

- `start_action` 必須提供有效 `action_id`，解析為 `StartAction(action_id, press_type)`。
- `speak_selection_or_clipboard` 不得提供 `action_id`，解析為 `SpeakSelectionOrClipboard`。
- Shortcut ID 與 normalized hotkey 必須唯一。
- 未知 command、缺少參數與不存在的 action reference 必須在啟動載入時失敗。

`ActionDefinition` 不包含 hotkey。Action catalog 只描述 LLM action，不得承載非 LLM command 的假 prompt 或假 output mode。

## Boundaries

- Platform listener：OS key events → ordered `ShortcutInputEvent` lifecycle。
- Shortcut catalog：`ShortcutPressInvoked` → typed command。
- Runtime：dispatch typed command。
- Services：執行 speech、action 等業務政策。

新增非 LLM 快捷功能時，必須新增 typed command 與明確的 shortcut command kind，不得在 Runtime 以 shortcut/action ID 字串特判。

Hotkey callback 必須把每個 `ShortcutInputEvent` 原樣 enqueue 到唯一的 app
command queue。Command resolution 只在 pump 內收到未被 guide quarantine 的
`ShortcutPressInvoked` 後執行。`ShortcutSequenceCoordinator` 擁有 sequence
waiting、timeout 與 rejection policy；`ShortcutCatalog` 保持 invoke fact 到
typed command 的 mapping，platform listener 不保存 sequence state。

`ShortcutPressId` 是公開的 typed lifecycle fact，不是 registry identity，
也不得被替代成 Workflow identity。Registry 不建立、結束或重用 press
identity。
