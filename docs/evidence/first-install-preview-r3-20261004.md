# Preview r3：新 key 刷新與 Windows 圖示

日期：2026-10-04。使用者確認 r2 重裝後仍顯示 generic rejected-key。

## 直接證據

使用者指定目前工作區 `.env` 保存新 key。首次對外驗證被自動核准審查
拒絕（只提供路徑不足以明確授權）；沒有繞過。使用者隨後明確允許一次
官方 Models API 唯讀驗證，回傳 HTTP 200、50 models、leaked=false。
沒有生成內容、輸出／另存 key 或原始 body。授權的一次請求已用完。
Installed Preview 的 gemini_errors/model_catalog/provider_settings 與 r2 build-source
byte hash 相同，支持實際安裝為 r2；不證明執行中 runtime identity。

已重現 Refresh Models 的兩處缺漏：UI 對 standard provider 不送出新 credential；
app adapter 也忽略其 connection credential。兩個 regression tests 修正前
2 failed、5 passed，修正後通過。Refresh 成功原先也清空尚未保存 key，
現在只有 successful save 才清空。使用者隨後確認 Validate and Save 成功，
保存後 Refresh 也成功；支持原拒絕來自刷新錯用舊 key 的路徑。
r3 實際安裝與 UI 驗收仍待使用者完成。

## 邊界診斷／簡短 ADR

分類 Yellow，推薦 local refactor，信心高。Trigger 是相似 credential 驗證
問題再次發生。保護既有驗證後才保存、失敗不切換 provider、single operation gate。

- Owner：ProviderConfigurationCoordinator 擁有 operation lifecycle；app backend
  解析本次輸入與 saved credential precedence；UI 只傳 typed intent 與呈現結果。
- 能力：所有 standard provider 都需要用當下輸入刷新模型，是通用編輯能力。
- Leakage：custom-endpoint capability 原先被錯當成「可傳新 credential」的判準。
- Enforcement：沿用 ModelCatalogConnection（credential repr=False），backend
  優先本次 key、空白 fallback saved；public command 與 backend tests 鎖定規則，
  UI apply test 鎖定 refresh 不清空、save 成功才清空。

Debt multiplier：如果逐一加入 Gemini/OpenAI/下一個 provider 的 UI 特例，
相同 credential precedence 與 editor lifecycle 要維護三份。接受現況成本低但
保留誤導錯誤；UI 特例增加 coupling；新 coordinator 重寫成本高且會重複 owner。
選既有 typed seam 局部修正，可直接回退。順序為 red tests → UI/backend
修正 → architecture/unit → native shortcut/bundle smoke → r3 Setup。
沒有新增 provider networking、persistence 或第二個 validation owner。
Review trigger：新的 provider editing 能力無法用既有 typed connection 表達時。
使用者已確認 Save／後續 Refresh 成功；最高價值下一個證據是 r3 輸入新 key
但尚未儲存時，直接 Refresh 成功且保留輸入。

## Windows integration

Setup 使用 ClipAI 現有 ico；打包獨立 setup-engine/clipai.ico 作穩定圖示位置。
Start Menu、desktop shortcuts 與 DisplayIcon 共用它。Desktop 透過 Windows
Known Folder API 取得，支援 OneDrive redirect；預設建立，不覆寫 existing link。
Native registry receipt 保存 desktop path，卸載先驗證 root/install ID 及
shortcut target/arguments；old install 沒 receipt 不刪桌面 link。

Unit cases：desktop create/remove、existing collision、changed target fail closed、
old receipt compatibility。Native smoke 唯一 Verification product 建立三個 shortcuts，
WScript COM 確認三者 ClipAI icon/target，validate/remove 成功，沒有啟動 app，
沒有更動使用者現有 Preview。證據位於 artifacts/first-install-diagnostic/shortcuts-*。

## 驗證與交付

完整 unit：1,876 passed、46 deselected；包含 architecture tests。
r3 build：preview-e1e20ba56ac24da6870eda2c8c53b941。
SHA-256：92b657ede5d36788f0aaab68c37ef2e192235de9661159f4a3a375008ff5b788。
完整新 bundle 在隔離 Verification root 安裝、installed refresh fix、native
integration 與 retained-data uninstall 通過，program_removed=true。
使用者實際 UI／翻譯驗收未完成。Unsigned local candidate，公開發行 gates 不變。
