# Selection capture implementation — automatic verification handoff

本次完成 G1–G8 與 G9 的自動驗證部分。使用者於 2026-10-11 明確指示：「本次先完成自動驗證，attended 留待稍後」。C4 實體按鍵驗證尚未完成，不能宣稱整份實作 prompt 已全部驗收。

## 實作與自動驗證

- SelectionCaptureCoordinator 先讀來源綁定的 UIA 選取；1.0 秒修飾鍵閘門只保護有正面選取證據的 copy fallback。
- core 擁有 27 個 SelectionReason 的封閉集合、guidance 對映及 outcome classification。Entry Panel 的 modifier_timeout 不自動使用剪貼簿，明確 UseEntryPanelClipboard 仍可使用凍結輸入。其他 unknown 的既有自動 fallback 保留。
- UIA worker 退休無法確認時先解除 owned pointer，下一次擷取建立新 worker；stop 仍保留清理失敗回報。退休／取消中的中斷回 cancelled。
- Popup 的 immutable RenderedContent 擁有 canonical text 和選取投影；唯讀 semantic_content 不讀 widget。Voice draft 編輯例外保留。Entry Panel × 與 tooltip 已調整。

以下數字皆來自落地 JSONL，不沿用 prompt 的範例數字：

| 證據 | 實測結果 |
| --- | --- |
| branch-loop.jsonl，成功 baseline | targeted 342、architecture 58、unit 2055 |
| branch-loop.jsonl，S6（自動模式） | targeted 420、architecture 62、unit 2141；全部成功；測試數未減少 |
| selection-policy-final-20261011.jsonl | 27 場景；seed 17/41/73 各 480 案 × 3 iterations；policy/exact rate 1.0；六項違規皆 0；nondeterministic=false；p95 0.028–0.066 ms（模擬） |
| selection-desktop-auto-20261011-3/4/5.jsonl | 三次獨立執行各 100/100；held 各 20/20 selected；剪貼簿各 100/100 保留；p50 23.519–24.750 ms、p95 41.574–44.472 ms（裝置） |
| selection-desktop-auto-final-20261011.jsonl | 分支迴圈最後一次 100/100；p50 25.354 ms、p95 52.579 ms |
| selection-integration-final-20261011.jsonl | 真實 Windows UIA integration smoke 1 案成功 |

所有本次 selection JSONL 與 branch-loop.jsonl 已掃描三個禁止的 fixture 字串，沒有原始內容。全回歸中的 65 個 integration tests 由 unit marker 排除，不能算成已驗證。另一次小範圍執行發現取消測試的 50 ms 排程競爭；只把取消情境的測試 deadline 設為 1 秒，逾時情境仍為 50 ms，正式 modifier timeout 仍為 1 秒。修改後相關 scripts/platform 測試 58 案全過。

## 人工驗證待辦

先前 attended loop 沒有取得實體操作證據，已依使用者指示結束。selection-desktop-attended-20261011.jsonl 保留原始失敗嘗試，不能用作 C4 成功證據；該次舊版 blocked 摘要漏算已輸出的 case rows，現已修正程式並新增拒絕測試。重新驗證必須另開完整 5 輪，不沿用失敗嘗試。

1. 以本分支重新啟動 ClipAI，確認實際 log 位置；原始碼模式通常是工作目錄的 logs/clipai.log，安裝版通常是 %LOCALAPPDATA%/ClipAI/logs/clipai.log。
2. 執行以下命令；若使用原始碼模式，額外指定 `--log logs/clipai.log`：

```powershell
.venv\Scripts\python.exe scripts/selection_desktop_loop.py --mode attended --rounds 5 --output artifacts/selection-desktop-attended-final.jsonl
```

3. 按受控視窗指示，操作 selected、modifier_held、held_after_open、caret_only 四狀態，共 20 案。只用實體按鍵，每案完成後 Esc 關閉 Panel。
4. 確認 exit 0、cases=passed_cases=20、held_after_open 全部 selected、no_capture_logged=0、clipboard_preserved=20。exit 3 是環境受阻，不能當成通過。
5. C4 通過後重新執行 `scripts/branch_loop.ps1 -Step S6 -Desktop`，保存最後證據。

## 文件與提交待辦

S7 尚未執行，ADR-0021、ADR-0016 superseded 註記及四份契約／架構／測試文件尚未回填。這遵守原 prompt「S6 全綠、證據落地後才回填」的限制。tracked 的 artifacts/selection-reliability.jsonl 尚未覆寫。

artifacts 原本被 .gitignore 忽略；本次提交範圍包含程式、測試與上述證據，S7 後續可引用已提交 JSONL 的數字。不要把三次桌面 auto 當成 attended hotkey 路徑的替代證據。
