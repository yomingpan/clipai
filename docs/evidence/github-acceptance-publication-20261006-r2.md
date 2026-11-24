# 交接準備期限修正配對：發布證據 2026-10-06 r2

使用者直接授權重新建置並發布；A 3.7.14 → B 3.7.15。
目前狀態：已於 2026-10-06 09:50:25 +08:00（`2026-10-06T01:50:25Z`）
公開為 prerelease，[Release](https://github.com/yomingpan/clipai/releases/tag/acceptance-20261006-r2)
ID `404226582`，`draft=false`、`prerelease=true`。

| Gate | 結果 | 證據 |
| --- | --- | --- |
| 工作區原始修正 | passed | 1,974 unit、56 architecture、完整 managed-bundle gate；見交接診斷 |
| 固定 B source archive | passed | 1,972 unit，64 integration deselected；140.52s；A／B source 僅版本差異 |
| A／B installed wheel | passed | 封裝 smoke 與獨立 `-I` probe；兩版預設 600s、virtual ready 78s 正常 App shutdown |
| A／B bundle／Setup | passed | 真實 Ed25519 admission、no-index wheel install、compiled extraction、精確 release asset verification |
| 一次性私鑰 | passed 已移除 | 最終 pair.json `private_key_removed=true`；不包含於 20 個發布檔案 |
| 遠端來源 tags | passed | 兩個 annotated tags 原子 push、ls-remote object／peeled commit 相符；未 push branch |
| GitHub 草稿完整 hashes | passed | 20 個名稱及完整 SHA256 相符；UI rounded sizes 記錄於 draft proof |
| GitHub 公開精確資產 | passed | 匿名 API 20 個名稱、精確 bytes、SHA256、uploaded state 與 proposal 相符；title／body／prerelease 相符 |
| 舊 Releases／production latest | passed 未變 | 三個舊 acceptance Release 與 v3.7.8 latest identity 前後相同 |
| 公開 catalog discovery | passed | 真實 release source adapter，3.7.14 選到 3.7.15，B hash／size／URL 相符 |
| 匿名整檔下載／B signature admission | passed | 20 個整檔 bytes／SHA256 全部相符；公開 keyring＋真實 Ed25519 verifier 接受下载 B 3.7.15 |
| 真實 About 更新 | failed（使用者回報） | 3.7.15 準備及交接成功；20 秒 health timeout 回復 3.7.14，舊版回報 healthy |
| 保留設定／reboot | pending | 尚無獨立實機驗收證據 |
| 乾淨 VM | deferred by user | 尚無乾淨 VM admission |
| 正式 Windows publisher | pending | unsigned technical Setup，正式發行仍 NO-GO |

來源與身份：

- A `acceptance-20261006-r2-a` → `abe4eb06349011be63bb0ddee0766bc87b871004`。
- B `acceptance-20261006-r2` → `35d5ec828e1a237f5280eda6e98fff5d11076a02`。
- A Setup SHA256 `6b8b4b19cc659dea3822d6a561ccee9e84bc99ea1ebf855af2faf63455dcdbc8`。
- A bundle SHA256 `5d4befbce92095b79af28386cc8b63567990a5ab41f179a65f2807da08ae77f2`。
- B Setup SHA256 `5208b3daecffc592d1ce6bd1fa3d3b65fb48719fb7c34d9c93acdb3c4ed4a7e7`。
- B bundle SHA256 `adb3d3df93cf718e4da50256eb75f16e5b0ed15a00b7f8f61f14b5908c175ae0`，20,659,703 bytes。
- keyring SHA256 `7a1022ece6b9b15d714f75e773d9fed7cc3cfeaf21889025ef3e9fc81a1da36f`。
- helper SHA256 `aa1511fadc88b1227218e840fb9e09353d293f651555e503c0f3b534eab475f8`。

本機可重跑證據在 `artifacts/about-handoff-timeout-20261006/`：
`candidate-sources.json`、`source-A-review.diff`、`source-B-review.diff`、
`frozen-source-verification.json`、`frozen-B-unit.log`、`installed-handoff-proof.json`、
`public-proposal.json`、`public-source-tags.json`、`public-baseline.json`、build logs。
草稿 proof：`draft-assets-verified.json`；公開 discovery：`public-discovery.json`。
公開 API proof：`artifacts/github-acceptance-publication-20261006-r2.json`。
匿名下載 proof：`artifacts/github-acceptance-download-20261006-r2-verified/download-verification.json`。
可重跑下載／簽章 verifier：`artifacts/verify-github-acceptance-20261006-r2.py`，exit 0。
大檔先以 canonical URL 的 range 請求遇 HTTP 500；單次完整 B 下載回應 200，
但 45 秒只收到 1,637,158 bytes 而逾時。改用標準 `?download=1` URL，
以 108 個 1 MiB 有限期限／重試 ranges 完成四個大檔，再組合核對整檔 SHA256。
部分 range 30 秒逾時後重試完成。Catalog URL 與 bundle URL 未因此改寫。
此驗證證明精確公開 bytes 與簽章，仍不代替 App 的連續下載或實際 About 更新。
公開頁截圖：`artifacts/github-acceptance-published-20261006-r2.png`。
固定 source archive 的 unit 數與工作區不同，因工作區另有兩個 acceptance helper
工具測試；發布的 helper 另外以精確 SHA256 識別，未假設它來自 App wheel。

最終配對：`artifacts/installer-acceptance-pair-20261006-r2/pair.json`。
精確 20 個公開資產：`artifacts/github-acceptance-20261006-r2/`。
工作區 HEAD／一般 index 保持不變；未修改使用者安裝、設定、keyring 或目前 App。

[測試步驟](../testing/github-acceptance-about-20261006-r2.md)。

後續實機回報已確認 handoff 修正有效，但完整更新尚未通過；
見[健康檢查期限診斷](about-health-timeout-20261006.md)。工作區修正需重新
建置穩定 launcher 才能交付；此 Release 的 20 個資產維持原 bytes。
