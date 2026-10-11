# Selection capture — completed verification

本次 G1–G9 已完成。使用者先前指示 attended 留待稍後，2026-10-11 恢復人工操作後，四狀態 × 五輪共 20 案全部通過；S6 最後回歸全綠並提交證據後，S7 已依實際行為回填。

## 實作與自動驗證

- SelectionCaptureCoordinator 先讀來源綁定的 UIA 選取；1.0 秒修飾鍵閘門只保護有正面選取證據的 copy fallback。
- core 擁有 27 個 SelectionReason 的封閉集合、guidance 對映及 outcome classification。Entry Panel 的 modifier_timeout 不自動使用剪貼簿，明確 UseEntryPanelClipboard 仍可使用凍結輸入。其他 unknown 的既有自動 fallback 保留。
- UIA worker 退休無法確認時先解除 owned pointer，下一次擷取建立新 worker；stop 仍保留清理失敗回報。退休／取消中的中斷回 cancelled。
- Popup 的 immutable RenderedContent 擁有 canonical text 和選取投影；唯讀 semantic_content 不讀 widget。Voice draft 編輯例外保留。Entry Panel × 與 tooltip 已調整。

以下數字皆來自落地 JSONL，不沿用 prompt 的範例數字：

| 證據 | 實測結果 |
| --- | --- |
| branch-loop.jsonl，成功 baseline | targeted 342、architecture 58、unit 2055 |
| branch-loop.jsonl，S6-attended | targeted 421、architecture 62、unit 2142；全部成功；測試數未減少 |
| selection-policy-attended-final-20261011.jsonl | 27 場景；seed 17/41/73 各 480 案 × 3 iterations；policy/exact rate 1.0；六項違規皆 0；nondeterministic=false；p95 0.042–0.051 ms（模擬） |
| selection-desktop-auto-20261011-3/4/5.jsonl | 三次獨立執行各 100/100；held 各 20/20 selected；剪貼簿各 100/100 保留；p50 23.519–24.750 ms、p95 41.574–44.472 ms（裝置） |
| selection-desktop-auto-attended-regression-20261011.jsonl | 最後 auto 100/100；p50 29.917 ms、p95 49.984 ms |
| selection-desktop-attended-run3-20261011.jsonl | 20/20；held_after_open 5/5 selected；no_capture_logged=0；clipboard_preserved=20；capture-log p50 31 ms、p95 47 ms |
| selection-integration-final-20261011.jsonl | 真實 Windows UIA integration smoke 1 案成功 |

所有本次 selection JSONL 與 branch-loop.jsonl 已掃描三個禁止的 fixture 字串，沒有原始內容。全回歸中的 65 個 integration tests 由 unit marker 排除，不能算成已驗證。另一次小範圍執行發現取消測試的 50 ms 排程競爭；只把取消情境的測試 deadline 設為 1 秒，逾時情境仍為 50 ms，正式 modifier timeout 仍為 1 秒。修改後相關 scripts/platform 測試 58 案全過。

## 人工驗證已完成與重新驗證指令

先前未操作的 loop、application_not_running 與暖身失敗均保留歷史，不合併為成功證據。正式接受的是 selection-desktop-attended-run3-20261011.jsonl 完整 20 案。原 harness 收到 capture log 就換場景，會打斷放開按鍵與 Esc；現在必須由操作人點「下一案」確認才推進。受控 WinForms 初次取得前景焦點時，native selection 已存在但 UIA 可回 caret-only；先取得前景焦點再設定 RichTextBox 選取可消除此重現。修正只在證據工具，不修改 production 政策。暖身失敗保留 status/reason 與剪貼簿比對，不計正式案數。

Attended 只讀 owned window token 的新增 content-free log；不讀文字回來做內容比對，也不能證明所有外部 app／UIA provider 都受支援。擷取時間不含人工按鍵等待與下一案確認。以下供未來重新驗證：

1. 以本分支重新啟動 ClipAI，確認實際 log 位置；原始碼模式通常是工作目錄的 logs/clipai.log，安裝版通常是 %LOCALAPPDATA%/ClipAI/logs/clipai.log。
2. 執行以下命令；若使用原始碼模式，額外指定 `--log logs/clipai.log`：

```powershell
.venv\Scripts\python.exe scripts/selection_desktop_loop.py --mode attended --rounds 5 --log logs/clipai.log --output artifacts/selection-desktop-attended-new.jsonl
```

3. 按受控視窗指示，操作 selected、modifier_held、held_after_open、caret_only 四狀態，共 20 案。只用實體按鍵，每案完成後放開按鍵、Esc 關閉 Panel，再點「下一案」。
4. 確認 exit 0、cases=passed_cases=20、held_after_open 全部 selected、no_capture_logged=0、clipboard_preserved=20。exit 3 是環境受阻，不能當成通過。
5. C4 通過後重新執行 `scripts/branch_loop.ps1 -Step S6 -Desktop`，保存最後證據。

## S7 文件

[ADR-0021](../docs/adr/0021-selection-modifier-release-scoped-to-copy-fallback.md) 記錄新的固定順序、實测證據、拒絕的替代方案與 review triggers。ADR-0016 已標示舊 gate 順序 superseded。selection-capture-contract、unified-entry-panel-contract、ARCHITECTURE_BOUNDARIES 與 TESTING_STRATEGY 已同步 core reason 所有權、modifier fallback、worker 自癒、immutable content 和兩種桌面驗證模式。

artifacts 原本被 .gitignore 忽略；本次提交範圍包含程式、測試與上述證據，S7 後續可引用已提交 JSONL 的數字。不要把三次桌面 auto 當成 attended hotkey 路徑的替代證據。
