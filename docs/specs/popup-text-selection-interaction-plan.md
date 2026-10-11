# Popup 文字選取互動改善計畫

日期：2026-09-23；修復驗證：2026-09-24。範圍：結果 Popup 的唯讀輸出與 Voice Draft 的可編輯／閱讀狀態。下列現況表記錄修復前的紅燈證據；修復後結果見本文末尾。

## Windows 參考行為與決策範圍

- [Microsoft Windows 滑鼠互動指南](https://learn.microsoft.com/en-us/windows/win32/uxguide/inter-mouse)：文字單擊設定插入點、雙擊選取字詞，第三擊可選取句子或段落；Shift 加單擊延伸連續選取。此頁明載是 Windows 7 時期的指南，因此只作互動慣例參考。
- [Microsoft Word 選取文字說明](https://support.microsoft.com/en-us/word/select-text)：拖曳選取範圍、雙擊選字、Ctrl+A 全選。Word 的段落操作屬於 Word 編輯器，不應推論為所有 Windows 文字框的唯一三擊規則。
- [Microsoft OneNote for Windows 說明](https://support.microsoft.com/en-us/onenote/highlight-notes-in-onenote-for-windows)：雙擊選字、三擊選整個段落，是文件型內容的具體 Windows 範例。
- [Windows Terminal 選取說明](https://learn.microsoft.com/en-us/windows/terminal/selection)：雙擊選字、三擊選行、Shift 加單擊延伸選取。這證明三擊的「句子／段落／行」須依內容模型決定。
- [Microsoft 文字選取設計指南](https://learn.microsoft.com/en-us/windows/apps/develop/input/guidelines-for-textselection)：可編輯與唯讀內容有不同互動狀態，建議盡量沿用平台文字控制項的選取能力。
- [Tk Text 官方手冊](https://web.tcl.tk/man/tcl8.7/TkCmd/text.html)：預設雙擊選字且後續拖曳按字詞擴選；三擊選邏輯行且後續拖曳按行擴選。

因此，不宜宣稱 Windows 全域規定「三擊必選段落」。ClipAI 應明訂符合自身內容的單擊、雙擊、三擊與拖曳規則，再把預期結果編成可重跑的驗收案例。

## ClipAI 現況與差異

| 互動 | Windows 參考／使用者預期 | ClipAI 現況與證據 | 判定 |
| --- | --- | --- | --- |
| 單擊、一般拖曳 | 設定插入點或從起點選取字元；唯讀區可選取文字 | `CTkTextbox` 沿用 Tk `Text` 類別綁定；尚待實機驗證 focus、拖曳及唯讀狀態 | 待驗證 |
| 雙擊 | 選取點擊處的字詞 | `install_script_aware_word_selection` 攔截雙擊，按空白、CJK、拉丁、其他四類選連續區段；連續漢字可能整段被選，標點可能成組被選 | 規則與 Windows 字詞語意未對齊；實機字詞邊界待比較 |
| 雙擊後拖曳 | 延續按字詞擴選 | 本機 Tk 事件重現：原生類別綁定得到 `beta gamma`、`selectMode=word`；ClipAI 綁定得到 `eta ga`、`selectMode=char`。自訂雙擊回傳 `break`，未設定 Tk 的拖曳選取模式 | **已重現缺陷** |
| 三擊與三擊後拖曳 | 文件型內容通常選句／段落；部分文字工具選邏輯行。拖曳維持相同粒度 | ClipAI 的雙擊 widget handler 會匹配第三下並回傳 `break`，阻斷 Tk 類別三擊綁定；自動重現三擊後仍只選 `beta`。只有額外安裝同 widget 的三擊綁定，Tk 原生選行才執行 | **已重現缺陷**；目前三擊實際停在字詞選取 |
| Shift 單擊／鍵盤擴選 | 從錨點延伸選取 | 繼承 Tk 類別綁定；雙擊自訂是否破壞原錨點與後續 Shift 行為尚待驗證 | 待驗證 |
| 右鍵 | 對已選文字開啟相關操作選單 | Tk `Text` 類別沒有 `<Button-3>` 預設綁定，ClipAI 的內容框也沒有右鍵選單綁定 | 可用性缺口；需確認產品要呈現哪些既有操作 |
| Ctrl+A | 全選當前文字區 | ClipAI 覆寫 Tk 預設，以 `1.0` 到 `end-1c` 全選 | 已明確實作；需雙模式驗收 |
| 選取後 Ctrl+C | 一次複製使用者看見的語意選取文字 | Tk 將 Ctrl+C 映射成 `<<Copy>>`，Popup root 同時綁 `Ctrl+C` 送 typed `CopyResult`。本機 Tk 事件重現兩個 handler 都被觸發；唯讀內容還含顯示專用換行提示，原生路徑可能先複製顯示字元 | **已重現雙路由**；剪貼簿結果待端到端驗證 |
| 選取文字供 Copy／Speak／Paste／Archive | 選中什麼就作用於什麼 | `BaseResultSurface.selected_text()` 投影 canonical 內容後呼叫 `.strip()`；邊界空白與換行會被去掉，空白選取回退到整份內容 | 與精確選取直覺有差異；更改前須處理既有 selection-first 契約 |

共用接縫位於 `ClipAI/ui/base_dialog.py`：`install_script_aware_word_selection`、`_PresentationTextbox`、`BaseResultSurface.selected_text()`；快捷鍵路由位於 `ClipAI/ui/result_dialog.py`。Voice Draft 與唯讀輸出共用 `content_text`，但切換 `normal`／`disabled`，閱讀模式會加入顯示專用換行提示。`docs/contracts/ui/base-dialog-surface-contract.md` 規定 editable 內容維持 canonical、唯讀提示不得流入輸出 intent；改善須守住此契約。

## 建議的目標互動

1. **共同基本動作**：單擊定位／清除舊選取、拖曳逐字元選取、雙擊選字詞、雙擊後拖曳逐字詞擴選、Shift 單擊延伸選取、Ctrl+A 全選，拖出框外時可繼續捲動選取。兩種內容狀態使用相同選取粒度；唯讀狀態禁止修改但可選取、複製。右鍵應提供符合當前狀態的選取操作；「複製」只在有 selection 時可用，「全選」選當前內容。右鍵 Copy 不得誤用 Popup Copy 的無選取全文 fallback；剪貼簿操作仍須透過 typed intent。Voice Draft 的剪下／貼上需另行核對既有編輯與 clipboard 契約。
2. **三擊**：建議選完整「語意段落／內容區塊」，三擊後拖曳逐段落擴選。Voice Draft 暫以空白行分隔段落，段內單一手動換行仍屬同一段；唯讀輸出使用既有 `PresentationBlock` 邊界，標題和每個清單項各自是一個區塊。`PopupRenderPlan` 可增加 typed block-offset 投影，避免 widget 重新解析 Markdown。視覺折行與 display hint 永遠不是段落邊界。把單一換行、空白行與段末換行的預期寫成 fixture 後，由自動 gate 驗證。
3. **字詞邊界**：維持 CJK／拉丁混排不跨文字系統的需求，但改為可檢驗的字詞規則；對空白、標點、連續漢字、日文、韓文、底線、數字、結合字元與 emoji 各有明確期望。以受控的 Windows 原生文字控制項自動擷取對照結果，不把整段同一文字系統直接當字詞。
4. **語意輸出**：Copy 按鈕和 Ctrl+C 走同一個 typed intent，且只作用一次；唯讀選取排除顯示提示、保留可見選取的語意內容。釐清僅選空白時是複製空白還是視作無選取，並同步更新 selection-first 契約。Voice Draft 編輯時 Ctrl+C 仍可複製所選文字，但不可同時觸發整份 Popup 輸出。

## 實作順序與驗收

1. **建立紅燈重現**：`scripts/popup_text_selection_gate.py` 以真實 `CTkTextbox` 和合成 Tk 事件重現三擊只選 `beta`、雙擊拖曳得到 `eta ga`；最初在 `normal`、`disabled` 各重跑三次，共 42 案、12 案穩定失敗。原生 Tk 對照案例均通過。執行 `.venv/Scripts/python.exe scripts/popup_text_selection_gate.py --repeat 3` 即得 JSONL 個案與退出碼。
2. **修正共用選取綁定**：讓自訂雙擊與 Tk 後續 `B1-Motion`、Shift 選取錨點共用一致的粒度狀態，或以單一 widget adapter 接管整個多擊選取生命週期；不要只補一個三擊 handler。只在 UI adapter 處理 toolkit 事件，不引入新的 Workflow／Voice Draft 狀態 owner。
3. **統一複製路由**：阻止 Tk 原生 `<<Copy>>` 與 Popup `Ctrl+C` 同時生效，按 Voice Draft 編輯與唯讀輸出明確選擇語意來源；透過既有 typed `CopyResult` 與 output lifecycle 執行 clipboard side effect。調整 `selected_text`／canonical 投影的空白規則時更新 `base-dialog-surface-contract.md` 和相關 tests。
4. **回歸驗證**：測試單／雙／三擊、每種粒度後拖曳、Shift 單擊與方向鍵、右鍵選單、Ctrl+A／Ctrl+C、失焦再聚焦、長文與拖出框外自動捲動、視覺折行、手動換行、Markdown 清單／標題、CJK 混排、IME、Voice Draft normal↔disabled 切換。Copy／Speak／Paste／Archive 使用相同 selection 的 canonical 文字；唯讀內容不得因 Ctrl+C 或點擊而可編輯。執行 UI targeted、architecture、unit suite 和 Windows interactive smoke。

### 自動循環驗證設計

- **第一層：真實 widget、合成事件**。gate 建立透明但已映射的 `CTkTextbox`，直接送進 Tk 的按下／放開／拖曳事件，讀取實際 `sel.first`／`sel.last`。固定時間戳與字元座標、每案例重建 widget；用固定測試文字，不需人工點擊，不使用剪貼簿或使用者資料。每案輸出 JSON，任一不符合即退出 1。修復後 `--repeat 3` 為 78/78 通過，`--repeat 20` 為 520/520 通過。
- **第二層：Popup 命令路由**。widget gate 驗證 Ctrl+C 僅進入 typed handler，沒有落入 Tk 原生 Copy 或 root 的第二條路由；Presenter 測試驗證 handler 送出一次 Copy。`BaseResultSurface` 的真實編輯／閱讀切換與 Markdown render 也在 gate 中受測，canonical 內容與首尾空白另由單元測試覆蓋。剪貼簿寫入本身使用既有 fake output-port 測試。
- **第三層：Windows 原生輸入 smoke**。`scripts/popup_text_selection_native_smoke.py` 在互動桌面建立自己的測試視窗，先確認原游標位置及該視窗為前景，再以真實 Windows 滑鼠輸入測三擊與雙擊拖曳，讀回 widget selection，最後恢復游標。它不使用使用者文字或剪貼簿。可編輯／唯讀共四案，連續三輪 12/12 通過。此層需有互動桌面及桌面輸入權限；一般 sandbox 內會在游標／前景能力檢查時停止。

## 驗證界限

- Voice Draft 與唯讀內容的三擊採語意段落；段內換行、清單項和段末換行的規則已由自動 gate 與單元測試驗證。Windows 應用之間沒有單一三擊標準。
- 顯示專用提示與 Markdown 樣式下的語意複製內容已有自動測試；實體滑鼠 smoke 尚未逐項核對每一種樣式的高亮範圍。
- 修復前的 Ctrl+C 雙路由已由事件重現；修復後的 gate 證實只有 typed 路由被觸發，但尚未操作使用者剪貼簿驗證最終內容。
- 右鍵選單的啟用狀態、選取專用 Copy 與全選已有 widget 自動測試；實體滑鼠 smoke 未涵蓋右鍵選單。

## 修復結果與驗證邊界

- 共用文字框的雙擊、三擊和拖曳現在有一致的字詞／段落粒度。唯讀結果依 presentation block 定位段落；Voice Draft 的編輯／閱讀切換保持相同選取行為。
- 內容框的 Ctrl+C 在 Tk 原生 Copy 前被攔截並進入 Popup typed Copy；右鍵提供「複製」和「全選」，未選文字時不會把整份內容當成右鍵 Copy。選取首尾空白與換行會保留到 Copy／Paste／Archive 內容。
- 自動 gate：78/78 通過；20 次重跑：520/520 通過。UI 與架構定向測試：380 通過；完整非 integration 單元套件：1,621 通過。真實 Popup 的既有 integration smoke：1 通過。
- Windows 原生滑鼠 smoke 在具互動桌面權限的執行階段完成，三輪 12/12 通過。合成事件與原生事件都驗證了可編輯／唯讀狀態的三擊段落和雙擊拖曳。其他非互動式單元測試可在一般 sandbox 執行。
