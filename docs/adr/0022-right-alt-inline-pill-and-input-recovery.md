# ADR-0022: Solo Right Alt、非啟用式 Pill 與鍵盤輸入復原

Status: accepted, 2026-10-21. Amends [ADR-0018](0018-inline-dictation-and-voice-capture-timing.md) and [ADR-0019](0019-inline-dictation-interaction-lifetime.md).

Right Alt 的意圖在放開時才成立；0.5 秒門檻事件只預覽。Inline
仍由 `VoiceInputController` 擁有一個非 Workflow 語意生命週期，並投影 frozen
`InlineDictationView`。Minimal 與 Choice 共用一個不取得焦點的 Pill；新安裝
預設 Minimal。依據：[solo 測試](../../tests/platform/test_right_alt_hotkey.py)、
[view 測試](../../tests/services/test_inline_dictation_view.py)、
[偏好測試](../../tests/platform/test_json_guidance_preferences.py)。

## 決策與邊界

- Platform 獨自管理 solo press、門檻、chord 取消及一次性的 Alt-up mask。
  閒置的短／長按皆開始錄音；錄音中或待決定時，短按選原文、長按選潤飾。
  自動停止不形成 delivery intent。見上述 solo/view 測試及
  [runtime 測試](../../tests/app/test_runtime_voice_input.py)。
- `InterruptionRuntimeModule` 獨自管理 current、all 與 CloseSession 的順序。
  Provider、Paste、clipboard transaction 的既有 owner 不變；UI 不直接執行
  這些副作用。見 [interruption 測試](../../tests/app/test_runtime_interruption.py)。
- UI owner 只接收 open、完整 view、close；以 interaction identity 拒絕舊投影及
  回呼。Pill 只持有 hover、animation、click lock 與 toolkit 資源。見
  [owner 測試](../../tests/ui/test_inline_dictation_owner.py)。
- 顯示依序為 anchor/DPI、place、記憶體背景擷取、draw、deiconify、
  show_without_activation、prevent_click_activation、animation。映射後先刷新
  Tk 的原生外框，再套用 native policy；外框必須在後續事件後仍有
  WS_EX_NOACTIVATE。單一視窗預留 review 空間，顯示後不移動。見
  [Pill 整合測試](../../tests/ui/test_inline_pill.py)。
- 調色盤與 raster 僅來自 `voice_visuals`。靜態 raster cache 只保留有界的
  幾何／顏色，不含 view identity、文字或背景；`TkRasterResources` 由 UI root
  持有一個不可見固定像素，重用 Tk 色彩表，在 root 銷毀前釋放。背景仍只活在
  該 Pill 視窗內。見 [視覺測試](../../tests/ui/test_voice_visuals.py)、上述 Pill
  資源生命週期測試及 [架構測試](../../tests/architecture/test_voice_visuals_contract.py)。

## D1–D12 定案

| 項目 | 實作結果與依據 |
| --- | --- |
| D1 | import 時凍結舊 TTS endpoint；每次新 endpoint 的 403 才 fallback；全域設定以 lock/finally 還原。[測試](../../tests/platform/test_speech_output.py) |
| D2 | 最近使用 1–3、分類 4–7；root 的 0 只提示「最近使用改為 1–3」。前五次開啟的 header 提示透過共用 preference gate 記錄。[coordinator](../../tests/services/test_entry_panel.py)、[preference](../../tests/app/test_runtime_user_preferences.py) |
| D3 | 預設僅 right_alt；不保留 Ctrl+Alt+M 第二綁定，也不抑制可列印 M。指南與 tray 提醒 AltGr 使用者改用 config/shortcuts.yaml 的 chord。[config](../../tests/app/test_config.py)、[hotkey](../../tests/platform/test_hotkey.py)、[guide](../../tests/services/test_shortcut_guide.py)、[tray](../../tests/ui/test_tray.py) |
| D4 | Popup 只有 CREATED/READING_INPUT → AWAITING_INPUT_CHOICE 且有 clipboard choice 才要求焦點。15 秒只關閉同 recovery、未聚焦、未釘選的 Workflow；未新增 keyboard-activity port。[測試](../../tests/ui/test_result_dialog.py) |
| D5 | typed `selection_uia_standby` 預設 true；false 維持 lazy。最多一個未綁定且已載入 CLR 的 standby。[單元](../../tests/platform/test_selection_uia.py)、[真實 worker](../../tests/platform/test_selection_standby_integration.py) |
| D6 | 按住 Right Alt 時點滑鼠不取消 solo。[測試](../../tests/platform/test_right_alt_hotkey.py) |
| D7 | Right Alt 與 Entry Panel 共用 0.5 秒門檻。[測試](../../tests/platform/test_right_alt_hotkey.py)、[Panel](../../tests/platform/test_entry_panel_hotkey.py) |
| D8 | trace stages、報表欄位與實體操作提示由 golden 鎖住；比較工具要求兩個固定 interval 各至少 20 次、同 cohort、p95 退化不超過 10%。[golden](../../tests/scripts/test_inline_observability_contract.py)、[compare](../../tests/scripts/test_inline_baseline_comparison.py) |
| D9 | 舊視窗測試的 DPI、bounds、Copy、lease、dwell、Esc 對應保存在 [覆蓋表](../evidence/right-alt-pill-test-coverage.md)；對應新 Pill、owner、runtime 測試通過後才刪除。 |
| D10 | 最近方塊高 66、最小寬 60、padding 10、badge 16、兩行省略號；tooltip 順序為標題、說明、長按、停用原因。中文括號與文案有 golden。[Panel](../../tests/ui/test_unified_entry_panel.py)、[文字](../../tests/ui/test_text_layout.py)、[guide](../../tests/ui/test_shortcut_guide_ui.py) |
| D11 | 潤飾後 settled view 保留 chosen=refine。[測試](../../tests/services/test_inline_dictation_view.py) |
| D12 | Panel 的 Enter 沿 master 找第一個 invoke，不使用 Popup 的 KeyboardConfirmGate；Panel 由長按 Alt 明確開啟。[測試](../../tests/ui/test_unified_entry_panel.py) |

Popup Enter 另要求取得焦點後 300 ms，新的無修飾按下與放開；auto-repeat、
先前已按住、失焦及隱藏選項都不能確認，每個 recovery id 最多一次。依據：
[gate](../../tests/ui/test_keyboard_confirm_gate.py)、[真實 Return 整合](../../tests/ui/test_input_recovery.py)。
聚焦時透過 injected `KeyboardStateReader` 取樣 Return 的實體狀態；app 組裝
重用既有 `windows_key_is_pressed`（VK_RETURN 也涵蓋 keypad Enter），UI 不直接
讀 Win32。已按住或讀取未知時，第一次延後 repeat/release 不得確認；看見 release
後才接受下一次新 press。這不是用來避免 typing 時 request focus 的活動監控。
依據：上述 gate/整合測試及 [平台映射](../../tests/platform/test_keyboard_state.py)。

## 否決方案與後果

拒絕 timer 直接送意圖、Right Alt 再開 Panel、M-key 特例、UI 推算 phase、
可啟用式 Choice 視窗、用通用 worker pool 執行 provider networking，以及新的
clipboard／Paste owner。上述拒絕由 solo、view、hotkey、owner 與架構測試鎖定。
AltGr 配置由使用者選另一個 chord，不在平台層猜測合成 Left Ctrl。

拒絕讓 UIA worker 在 interactive capture 路徑等待 200 ms 的 CLR 正常退出。
read-only owned worker 改為 kill/reap，沿用原有 worker registry 與 stop 預算，
未建立另一個退休 queue。依據：[cleanup 回歸](../../tests/platform/test_selection_uia.py)
及 [worker lifecycle](../../tests/platform/test_selection_worker_lifecycle.py)。

## 桌面證據與限制

[S8 gate](../../artifacts/mu-s8-release.jsonl) 為 passed，content_leak=false。

| 實測 | 證據 |
| --- | --- |
| Notepad / Word / Edge textarea × ✓ / ✦，6/6；show/click foreground、focused control、intent 皆通過 | [focus JSONL](../../artifacts/mu-s8-focus-mapped.jsonl) |
| standby 開啟，新來源 50/50；p50 174.423、p95 238.293 ms，無 >1000 ms、unknown_as_none=0 | [on](../../artifacts/mu-s8-standby-on-retire.json) |
| standby 關閉對照，新來源 50/50；p50 755.903、p95 855.851 ms | [off](../../artifacts/mu-s8-standby-off.json) |
| 最多兩 worker，private 48.039 / 48.004 MB；stop 後零殘留 | [on](../../artifacts/mu-s8-standby-on-retire.json)、[清理](../../artifacts/mu-s8-final-cleanup.json) |
| 236 個 fractional-alpha 邊緣像素，黑邊 0；未保存影像 | [pixel](../../artifacts/mu-s8-pixel-root-resources.json) |
| 同 cohort 各 20 次；首次畫面 p95 47 → 47 ms，stop→dispatch p95 547 → 516 ms；20/20 唯一受控貼上配對 | [compare](../../artifacts/mu-s8-final-comparison.json)、[pairing](../../artifacts/mu-s8-final-pairing.json) |
| 535 targeted、64 architecture、2341 unit，零失敗；另 9 個 Tk integration 通過 | [loop](../../artifacts/mu-loop.jsonl)、[integration](../../artifacts/mu-integration.jsonl)、[Pill tests](../../tests/ui/test_inline_pill.py) |
| S9 補上外部 held/unknown Enter 快照後，547 targeted、64 architecture、2343 unit；4 個 recovery integration 與實際組裝啟停通過 | [最終 gate](../../artifacts/mu-final-release.jsonl)、[recovery](../../tests/ui/test_input_recovery.py)、[smoke](../../artifacts/mu-s9-composition-smoke.json) |

首次畫面起點為 shortcut admission，終點為 Tk viewable + DwmFlush observer，
不是 HID key-down 或精確像素時間。正式延遲 cohort 僅涵蓋本機 Windows、
Minimal、raw、zh-TW、受控 Tk 目標；不外推到 refine、其他裝置或 Teams。
Paste dispatch 仍不是產品對插入成功的確認。第一輪 63 ms 的失敗對照與焦點
回歸均保留在 artifacts，未改判為通過。以上限制見 [報表](../../artifacts/mu-s8-controlled-final-report.json)
及 [失敗對照](../../artifacts/mu-s8-baseline-comparison.json)。

再出現 native wrapper 更換、第二個語意 owner、背景跨視窗保存，或新裝置超過
上述預算時，重新診斷；不可用模擬時間替代桌面證據。
