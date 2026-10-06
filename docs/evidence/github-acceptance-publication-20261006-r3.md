# GitHub health timeout acceptance — 2026-10-06 r3

使用者已直接授權建置並發布 A 3.7.16 → B 3.7.17。
目前狀態：[Release](https://github.com/yomingpan/clipai/releases/tag/acceptance-20261006-r3)
已於 2026-10-06 10:45:33 +08:00（2026-10-06T02:45:33Z）公開為
prerelease，ID 404256924；`draft=false`、`prerelease=true`。

| Gate | 結果 | 證據 |
| --- | --- | --- |
| 工作區修正 | passed | 42 targeted、1,989 unit（含 56 architecture）、完整 managed-bundle gate |
| 固定 B source archive | passed | 1,987 unit、64 integration deselected；119.13s；A/B 只差版本號 |
| A／B installed wheel | passed | 隔離 `-I` 的實際 installed wheels，各 owner 120s 預設、virtual 30s／120s healthy、缺訊號 120s timeout |
| A／B bundle／Setup | passed | 簽章 admission、offline install、compiled extraction、asset consistency |
| 一次性私鑰移除 | passed | final pair proof `private_key_removed=true`／file absence |
| 精確來源 tags | passed | 兩個 tags 原子 push；不 push branch |
| GitHub 草稿完整 hashes | passed | UI 20 個檔名及完整 SHA256 均符合 proposal；保存後再發布 |
| GitHub 公開精確資產 | passed | 20 個名稱、精確 bytes／SHA256、uploaded state／body／prerelease |
| 舊 Releases／正式 latest | passed 未變 | 四個舊 acceptance 與 v3.7.8 identity 前後相同 |
| 公開 catalog discovery | passed | 真實 release adapter：3.7.16 選到 3.7.17，B identity 相符 |
| 匿名完整下載及簽章 | passed | 20 檔 bytes／SHA256 相符，公開 keyring／真實 Ed25519 verifier 接受 B 3.7.17 |
| 真實 About 更新 | passed（使用者回報） | 2026-10-06 使用者確認成功更新至 3.7.17 |
| 保留設定／reboot | pending | 尚未收到本輪個別驗收結果 |
| 乾淨 VM | deferred by user | 使用者目前無環境 |
| 正式 Windows publisher | pending | 本輪 unsigned technical prerelease |

來源：A `748c445380096c1df18569586e494f68f23c8875`；
B `a890c2f4c7ba83d4fbc5703e0be50f158c9c0206`。
tags：`acceptance-20261006-r3-a`／`acceptance-20261006-r3`。
正常 HEAD `b3422eb04bcdbb58300642498322e5aa458d205c`／index 保持不變。

建置／來源／封裝 probe 在 `artifacts/about-health-timeout-20261006/`；
final pair 在 `artifacts/installer-acceptance-pair-20261006-r3/`；
精確 20 個公開檔案於 `artifacts/github-acceptance-20261006-r3/`。

- A Setup SHA256 `22af4207f2a355dcd0696799ff7d552faad2a512cf13a98cbb327b60516ee3d8`。
- A bundle SHA256 `b641f7236b1595ec2cefed5ff128e146a9b02dad1f4e58d3097bc1d17704d269`。
- B Setup SHA256 `7fbce9c314a838c946666519c551e28f6cc1834254bb19272e7a75ae270390bd`。
- B bundle SHA256 `a49a5052aa72900e881864d15830b600af471063f938727a10a616982c7803ca`，20,660,308 bytes。
- 公鑰 keyring SHA256 `4e5c6a3c3ed3e322d8895a8eb088a638f53676af2c56e6412a0c1aab7a777dc2`。
- helper SHA256 `aa1511fadc88b1227218e840fb9e09353d293f651555e503c0f3b534eab475f8`。

公開 API proof：`artifacts/github-acceptance-publication-20261006-r3.json`。
公開頁截圖：`artifacts/github-acceptance-published-20261006-r3.png`。
建置、來源、installed startup、tags、草稿及 discovery proofs 都位於上述
`about-health-timeout-20261006` 目錄。

續作時發現驗證腳本沿用了 r2 的本機輸出名稱，已中止、修正並把 r3
partial chunks 移到經檢查的獨立 r3 目錄。舊 r2 downloaded proof 的 20 個
檔案重新核對大小／SHA256，完全未變。r2 公開 API 本機報告還原成
發布前 baseline 中的 r2 record；GitHub 舊資產和 releases 沒有修改。

匿名下載 proof：`artifacts/github-acceptance-download-20261006-r3-verified/download-verification.json`。
可重跑 verifier：`artifacts/verify-github-acceptance-20261006-r3.py`，exit 0。
四個大檔共 108 個 1 MiB bounded ranges，使用標準 `?download=1` URL
suffix，部分 30 秒 partial read timeout 後在有限重試內完成。組合後完整
SHA256 通過；Catalog URL 未改寫。這不是使用者 App 的連續下载成功證據。
2026-10-06 使用者回報「成功了 更新到3.7.17」，實際 About 更新標記為
passed（使用者回報）。本次未另外收集事件紀錄或 health receipt；設定保留／
reboot 仍 pending，乾淨 VM 仍依使用者要求 deferred。

工作區與固定 source 的 unit 數不同，因另有兩個 acceptance helper 工具測試
尚未固定在 App source；本次發布的 helper 另外以精確 SHA256 識別。
健康檢查的 timing probes 使用模擬時鐘和真實 typed artifact store，
不代替使用者電腦的完整 About 更新成功證據。

[診斷及回歸](about-health-timeout-20261006.md)、
[實機步驟](../testing/github-acceptance-about-20261006-r3.md)。

2026-10-06 本對話續驗：使用者下載 helper 並核對上述 SHA256 後，
`--timeout-seconds 1200` 被 helper 的 30–600 秒限制拒絕；改以 600 秒
重跑後回報「成功了。可以準備發行正式版 規劃一下」。本輪 About 更新
passed（使用者回報），沒有另外收集版本畫面或交易／health receipt；
設定保留、捷徑重開與 reboot 不由此推論通過。已修正 r3 runbook 的參數。
後續見[正式版發行計畫](../specs/official-release-plan-20261006.md)。
