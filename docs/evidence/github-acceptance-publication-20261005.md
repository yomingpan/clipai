# GitHub 修正候選發布證據：3.7.10 → 3.7.11

日期：2026-10-05，Asia/Taipei。範圍：使用者直接授權「好 發布」的測試 prerelease。

[公開 Release](https://github.com/yomingpan/clipai/releases/tag/acceptance-20261005)
ID `403862275`，2026-10-05 23:31:22 +08:00 公開，`draft=false`、`prerelease=true`。

| Gate | 結果 | 證據 |
| --- | --- | --- |
| A/B source tags | passed | `acceptance-20261005-a` → `a2afb79c204a0bc5ae5688e77141540e862e58cf`；`acceptance-20261005` → `06b44cae73dfa1126ea5ee2ef5d86f4544030ffa` |
| Draft 資產 | passed 名稱與 SHA256 | 20 個核准檔案全部完成；UI 尺寸為四捨五入顯示 |
| 公開 API exact assets | passed | 20 個名稱、精確 bytes、SHA256 與 uploaded state 完全符合本機 proposal |
| Production latest | passed 未變更 | API 前後皆 `v3.7.8`、同一 release ID |
| 舊 acceptance release | passed 未變更 | ID、body、published_at、每個 asset ID/name/size/digest 前後相同 |
| 公開 catalog discovery | passed | 真實 `HttpsManagedReleaseSource`／`UrllibManagedUpdateTransport`，3.7.10 選到 3.7.11；只做 discovery |
| 匿名整檔下載／B signature admission | passed | 20 檔整檔 SHA256／精確 bytes；B Ed25519 admission 通過 |
| 使用者實際 About 更新／設定保留／重開 | pending | 尚未把 discovery 或資產驗證當成更新成功 |
| 乾淨 VM | deferred by user | 使用者目前沒有 VM 或第二台電腦 |
| 正式 Windows publisher／native-license admission | pending | 測試 Setup unsigned，正式公開發行仍 NO-GO |

推送命令：`git push --atomic origin refs/tags/acceptance-20261005-a refs/tags/acceptance-20261005`。
遠端 annotated tags 已逐一 peel 並比對上述 commit；未推送 branch。
HEAD 仍 `b3422eb04bcdbb58300642498322e5aa458d205c`，一般 index 沒有 staged diff。

本機證據：

- `artifacts/about-acceptance-20261005/public-proposal.json`：核准 20 檔案集合與精確 hashes。
- `artifacts/about-acceptance-20261005/draft-assets-verified.json`：發布前 UI name/hash/rounded-size。
- `artifacts/github-acceptance-publication-20261005.json`：匿名公開 API、舊 release／latest 比對。
- `artifacts/about-acceptance-20261005/public-discovery.json`：公開 catalog 的實際來源選擇。
- `artifacts/verify-github-acceptance-20261005.py`：匿名下載與 B admission 的可重跑驗證。
- `artifacts/github-acceptance-published-20261005.png`：已公開 prerelease 畫面。

發布前計畫原先要求 exact bytes；草稿 UI 僅提供四捨五入尺寸，名稱與完整 SHA256
已逐一核對，精確 bytes 在公開後 API 通過。此處保留實際驗證順序，沒有宣稱
發布前取得了未讀到的 API 精確 byte 長度。

同一 B bundle SHA256 `33844a885d107f1321c65394f63ccfb6ffc18d64c98756be3537669ba6331ec3`
供 Setup B 與本次 About catalog 使用。A/B 共用一次性 authority，私鑰未上傳。
已發布的 20 個檔案不再重寫；人工步驟見
[About 實測](../testing/github-acceptance-about-20261005.md)。

匿名驗證命令：`python artifacts/verify-github-acceptance-20261005.py`（repo PYTHONPATH）。
四個大檔透過 108 個匿名 HTTPS range requests、有界重試後重組，整檔 hash
與全部精確 bytes 通過；其餘 16 檔由匿名 HTTPS GET 驗證。B bundle 再以公開
keyring、封裝 ssh-keygen 與 `VerifiedManagedBundleStager` 做真實 Ed25519
signature admission，manifest app version 為 `3.7.11`。

證據：`artifacts/github-acceptance-download-20261005-verified/download-verification.json`。
網路分段曾遇到 timeout 並重試；此 gate 僅證明資產內容、可取得性與簽章，
不把它記成使用者 About 的單次連續下載／交接成功。
