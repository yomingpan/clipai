# 3.7.18 Windows 簽署選項

查核日期：2026-10-06。這是可審核的選型提案，未購買、申請、接受條款或傳送身分資料。

## 目前事實

- 本機 CurrentUser/My、LocalMachine/My 未列出可用 code-signing 憑證；未找到
  Windows SDK SignTool。這不代表其他帳號／外部服務一定沒有 signer。
- GitHub Repository secret `CLIPAI_MANAGED_UPDATE_PRIVATE_KEY` 存在；正式 key ID
  與公鑰 vars 亦存在，key ID 為 `clipai-managed-update-release-2026-09-r3`。
  只查核存在與公开設定，未讀取或輸出私鑰；實際私鑰使用仍需 CI self-verification。
- Managed Ed25519 簽章驗證更新內容；Windows Authenticode 驗證 EXE publisher。
  兩者是不同信任鏈，前者不能填補後者的 gate。
- 本地 Git tracked files 未找到 first-party LICENSE／COPYING；尚未決定專案授權。

## 可用路徑

| 路徑 | 成本與條件 | 本輪建議 |
| --- | --- | --- |
| SignPath Foundation | 合資格 OSS 免費；須符合 OSI license、來源建置、審核與其簽署政策 | 若確定開源，可先評估；目前授權未定，不能保證接受或時程 |
| SSL.com IV + eSigner | IV 頁面一年 US$129；eSigner IV/OV 最低 US$180/年或 US$20/月，另計憑證 | 若用個人名義且願意付費，列為候選；先確認所在地資格、checkout 總價與身分驗證 |
| Microsoft Artifact Signing | Public Trust 個人目前限美國／加拿大；組織有另列地區資格 | 未確認發行者資格前不選用，不以部署區域替代合法所在地 |
| 明確未簽署發行 | 不支付 publisher 簽署費，但最終 Setup 沒有已驗證 Windows publisher | 現行正式 gate 不允許；必須由維護者明確調整政策，保留未簽署的事實與其他 admission |

SSL.com IV + eSigner 按目前一年憑證與年繳服務相加為 **US$309/年**，是網站
標價試算，不是訂單或報價；稅費、資格、加購與 native 檔案簽署數量尚未核定。
IV 需要個人身分驗證；證書會使用已驗證的個人姓名。
來源：[IV 產品／價格](https://www.ssl.com/products/software-integrity/code-signing/iv/)、
[eSigner 價格](https://www.ssl.com/guide/esigner-pricing-for-code-signing/)。

SignPath 的免費路徑須符合其開源與來源驗證條件；可能由 Foundation 作為 publisher。
目前不能自行替 ClipAI 授權或承諾第三方審核結果。
來源：[免費 OSS 服務](https://signpath.org/)、[條件](https://signpath.org/terms)。

Microsoft 的地區／個人身分條件以目前 quickstart 為準；本輪未推論使用者所在地
或法定發行者身分。
來源：[Microsoft quickstart](https://learn.microsoft.com/en-us/azure/artifact-signing/quickstart)。

## 簽署後如何完成發行

1. 固定 publisher 與 signer，確認原生元件及 venv redirector 的簽署／上游來源
   審核範圍；SignPath 不承諾替本專案簽署第三方原生檔案。
2. 更新固定 inputs，完成 dependency/native notices 與散布 admission。
3. 使用同一份 managed bundle 建置正式 `ClipAI.Desktop` Setup，再簽署與 timestamp。
4. 簽署會改變 Setup bytes，重新封存 provenance、hashes 與受影響驗收證據。
5. 跑 release-ready verifier 並驗收最終下載檔案。

簽章提供 publisher／完整性驗證；新簽署檔案仍可能出現 SmartScreen reputation
提示，不能承諾沒有警告。[Microsoft code-signing 說明](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options)。

Windows 簽署以外，現行 Preview verifier、正式 inputs admission、乾淨機／reboot／
跨登入／新手觀察亦各有門檻；完成付款不代表這些 gate 自動通過。

## 需要維護者決定

若接受等待 OSS 申請，先決定 ClipAI 是否使用開源授權；若願意付費，確認
發行者身分、可接受費用並由本人完成必要身分驗證／付款。若選擇未簽署，
明確核准發行政策調整，Agent 再同步修改契約、實際驗證與公開說明；本提案
尚未執行任何例外或購買。
