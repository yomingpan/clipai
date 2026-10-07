# GitHub Windows venv 修正候選發布證據：3.7.12 → 3.7.13

日期：2026-10-06，Asia/Taipei。使用者直接授權「好發佈」的精確測試配對。

[公開 Release](https://github.com/yomingpan/clipai/releases/tag/acceptance-20261006)
ID `404200744`，2026-10-06 08:52:13 +08:00（`2026-10-06T00:52:13Z`）公開，
`draft=false`、`prerelease=true`。

| Gate | 結果 | 證據 |
| --- | --- | --- |
| A/B source tags | passed | `acceptance-20261006-a` → `3ac5d70d2a2c5d6d132ca868bd9a328e00b59044`；`acceptance-20261006` → `b6f921ec163e50aaeb53dcac494767a3ac3d4e5a` |
| Draft 資產 | passed | 20 個名稱、完整 SHA256 與 UI 四捨五入尺寸符合核准 proposal |
| 公開 API exact assets | passed | 20 個名稱、精確 bytes、SHA256、uploaded state 符合本機 proposal；body／title／prerelease 亦符合 |
| Production latest | passed 未變更 | 前後仍 `v3.7.8`、同 ID／body／published_at／asset identities |
| 舊兩個 acceptance releases | passed 未變更 | ID／body／published_at／asset ID、name、size、digest、state 前後相同 |
| 公開 catalog discovery | passed | 真實 `HttpsManagedReleaseSource`／`UrllibManagedUpdateTransport`，3.7.12 選到 3.7.13 |
| 匿名整檔下載／B signature admission | passed | 20 檔精確 bytes／整檔 SHA256；B 真實 Ed25519 admission 通過 |
| 使用者實際 About 更新 | failed（使用者回報） | 另一台電腦 App 在 20s handoff_timeout；host 在 78s ready，之後 shutdown_failed；見交接期限診斷 |
| 設定保留／重開 | pending | 未完成實際更新成功驗收 |
| 乾淨 VM | deferred by user | 未提供乾淨 VM；另一台電腦測試不代表乾淨 VM admission |
| 正式 Windows publisher／native-license admission | pending | Setup unsigned，正式發行仍 NO-GO |

原子推送：`git push --atomic origin refs/tags/acceptance-20261006-a refs/tags/acceptance-20261006`。
遠端 annotated tags 逐一 peel 並比對上述 commit；未推送 branch。
HEAD 仍 `b3422eb04bcdbb58300642498322e5aa458d205c`，一般 index 無 staged diff。
沒有終止使用者 app、改寫已安裝 keyring／設定或移除使用者資料。

本機可重跑證據：

後續實測失敗與修正記錄見[交接期限診斷](about-handoff-timeout-20261006.md)。
本次公開資產保持原 SHA256；工作區的期限修正尚未包含於 3.7.12／3.7.13。

- `artifacts/about-identity-20261006/public-proposal.json`：核准 20 個檔案集合與精確 hashes。
- `artifacts/about-identity-20261006/public-source-tags.json`：直接授權、push 範圍、遠端 tag／commit。
- `artifacts/about-identity-20261006/public-baseline.json`：發布前匿名 API 舊 Release／latest 基線。
- `artifacts/about-identity-20261006/draft-assets-verified.json`：發布前草稿 UI 名稱／完整 SHA256／rounded sizes。
- `artifacts/github-acceptance-publication-20261006.json`：發布後匿名 API exact assets／舊 Release／latest 比對。
- `artifacts/about-identity-20261006/public-discovery.json`：公開 catalog 的實際來源選擇。
- `artifacts/verify-github-acceptance-20261006.py`：匿名下載／整檔 SHA256／B admission。
- `artifacts/github-acceptance-published-20261006.png`：已公開 prerelease 畫面。

發布前名稱與完整 SHA256 已核對；UI 尺寸只是四捨五入值，精確 bytes 在公開後
API 核對，未宣稱發布前讀到未取得的精確 API byte 長度。

同一 B bundle SHA256 `ffeb63a0d234b4f62362433f1326fc0722d85342c4d56912389f0218887a4153`
供 Setup B 與本次 About catalog 使用。A/B 共用新的配對 authority，私鑰已刪除
且未上傳。20 個公開檔案保持 immutable；實際修正與仍需 A Setup 的原因見
[診斷證據](about-identity-ineligible-20261006.md)。

匿名驗證命令：

```powershell
.venv/Scripts/python.exe artifacts/about-identity-20261006/verify_publication.py post
$env:PYTHONPATH = (Get-Location).Path
.venv/Scripts/python.exe artifacts/about-identity-20261006/verify_discovery.py
.venv/Scripts/python.exe artifacts/verify-github-acceptance-20261006.py
```

整檔驗證 passed，記錄保存於
`artifacts/github-acceptance-download-20261006-verified/download-verification.json`。
四個大檔經 108 個匿名 HTTPS range requests、有界重試後重組；其餘 16 檔由
匿名 HTTPS GET 取得。逐一比對 20 檔的完整 SHA256 與精確 bytes。部分分段請求
曾達 30 秒逾時並重試，最終全部通過；B 再以公開 keyring、封裝 ssh-keygen
與 `VerifiedManagedBundleStager` 驗證，manifest app version 為 3.7.13。
分段下載 gate 只證明匿名可取得性、精確內容與簽章；不作為使用者 About
單次連續下載／交接成功證據。人工步驟見[新配對實測](../testing/github-acceptance-about-20261006.md)。
