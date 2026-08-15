# Web Speech 個人化可行性實驗

這是刻意保持一次性、僅在瀏覽器本機執行的 N-of-1 實驗。它不會整合到 ClipAI、也不會送出網路請求；目標是回答：**Web Speech 能否維持第一層 ASR，並由 ClipAI 式的修正記憶降低重複修正成本？**

## 如何執行

1. 用桌面版 Chrome 開啟 `index.html`。若 `file:` URL 不能使用麥克風，可在儲存庫根目錄執行：

   ```powershell
   python -m http.server 8000 -d experiments/web-speech-personalization
   ```

   再開啟 `http://localhost:8000`，並允許麥克風。
2. 先按「執行能力診斷」。它會記錄瀏覽器識別資訊、`SpeechRecognition`、`SpeechRecognitionPhrase`、`processLocally`，以及 `available({ langs: ['zh-TW'], processLocally: true })` 的結果。
3. 分別選擇「遠端／預設」與「本機 on-device」路徑，勾選「驗證原生短語偏誤」，各以一筆真實錄音測試。短語成功或 `phrases-not-supported` 都會被保存。不能因物件存在就宣稱短語偏誤可用。
4. 蒐集教學資料：每次將最終辨識修正為實際說出的文字再接受。只有「本句明確填入」的技術詞彙，且誤辨可縮成一個英文 token（例如 `streamlet → Streamlit`），才會成為候選別名；整句、中文片段、標點與多詞差異不會建立規則。相同別名至少成功確認兩次、可靠度至少 0.80 後，才會自動套用。
5. 蒐集受控成對評估：三個類別都要有資料。
   - A：已學得的詞彙；預期可看見修正記憶改善。
   - B：未見技術詞彙；檢查是否過度套用舊規則。
   - C：純中文控制組；「預期技術詞彙」必須留空。
6. 每次最終辨識都會由同一個 raw top-1 產生三欄：A 原始、B 修正記憶、C 修正記憶＋保守情境。只選一欄作為實際人工修正起點；其他欄只會與您最後確認的文字做成對反事實比較，不會偽造人工時間。
7. 匯出 JSON／CSV，再查看 A、B、C 分開的結論。

## 原生短語偏誤的判讀

- `SUPPORTED`：遠端／預設辨識的真實短語測試成功。
- `SUPPORTED ONLY ON-DEVICE`：僅本機辨識的真實短語測試成功。
- `UNSUPPORTED FOR zh-TW`：診斷明確回報本機 zh-TW 語言包不可用。
- `UNSUPPORTED IN CURRENT ENVIRONMENT`：遠端與本機測試都被拒絕。
- `UNKNOWN`：診斷 API 不可用、尚未完成兩種真實測試，或結果不完整。

`phrases-not-supported` 表示當次辨識引擎拒絕短語；頁面會停止那一次原生短語測試，絕不悄悄改以無偏誤模式重試。不過 A/B/C 後處理實驗仍可進行，因為它不依賴原生短語 API。

## 指標與結論門檻

- 決策主軸：選定輸出「已顯示→接受」的中位數／p95、重複錯誤率、有害修正數、免編輯接受率。
- MER 將漢字逐字切分、連續英文／數字視為一詞，並忽略標點與空白。
- 技術詞彙只依「實際說出的預期詞彙」計算；純中文組不計算。詞彙精確率在本實驗僅作受限的提示，因為它只知道已確認詞表而非完整詞典。
- 不以 Web Speech confidence 作決策：若它在樣本間不變（例如全為 `1`），便沒有辨識力。
- 有害修正指 B 或 C 相比原始輸出，距離最後人工確認文字更遠。任何非零有害修正都應先停下來檢查規則，不應把它包裝成改善。

這是單人、配對輸出的可行性證據，不是母體結論。原始、記憶、記憶＋情境必須分開判定；只有在成本下降、重複錯誤低、有害修正為零且免編輯接受率足夠時，才適合讓 Web Speech 繼續擔任第一層 ASR。

## 本機資料與回歸檢查

資料保存在目前 Chrome 設定檔的四個具命名空間的 `localStorage` keys：樣本、詞彙、修正記憶與能力診斷。清除前請先匯出 JSON。

舊版匯入的整段修正規則會自動停用；它們不會影響新的比較。可在頁面按「清除修正記憶」後重新建立安全別名。

可執行以下無麥克風回歸檢查：

```powershell
node experiments/web-speech-personalization/test-harness.mjs
```

它會驗證修正規則必須已有足夠成功確認，且 `phrases-not-supported` 以繁體中文呈現並且不會靜默降級。
