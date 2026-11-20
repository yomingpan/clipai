# 新測試配對發布提案：3.7.10 → 3.7.11

狀態：使用者已直接授權「好 發布」；已公開為 prerelease。20 個遠端資產的名稱、精確 bytes 與 SHA256 通過；20 檔匿名下載／整檔 SHA256 及 B 簽章 admission 全部 passed。
目的：重新驗收 About 下載、取消與交接；不改正式 latest 或舊公開資產。

## 精確發布範圍

- Repository：`yomingpan/clipai`。
- 保存 A 來源的 tag：`acceptance-20261005-a` →
  `a2afb79c204a0bc5ae5688e77141540e862e58cf`，不建立另一個 Release。
- 本次 Release tag：`acceptance-20261005` →
  `06b44cae73dfa1126ea5ee2ef5d86f4544030ffa`。
- Title：`ClipAI installer/update acceptance — 3.7.10 to 3.7.11`。
- 先 draft、上傳完整檔案、核對 remote 名稱／長度／SHA256，再以
  `prerelease=true`、`make_latest=false` 公開。
- 不替換 `acceptance-20261004` 或 `v3.7.8`，不修改已安裝 keyring／設定。

上傳目錄：`artifacts/github-acceptance-20261005/`。共 20 個檔案，包括 A/B Setup、
各自唯一 bundle、公用 keyring、catalog、notices、證據、helper 與 SHA256 清單。
本文供審核；實際 Release body 已備於該目錄的 `release-body.md`。

| 候選 | Setup SHA256 | bundle SHA256 |
| --- | --- | --- |
| A 3.7.10 | `a7df1f5e329b58ea38c1f123d1787f9af1b21b24a6fb65ee2cdf5a87219d6f1c` | `fbb9eadb3eb5d5fdcb481a35c133c820b07fb5e7605d79ae00312954c421d0f1` |
| B 3.7.11 | `726cf825fea31c56180fc008cae146c9640fc30b17345b2ecf88917afbbf5e27` | `33844a885d107f1321c65394f63ccfb6ffc18d64c98756be3537669ba6331ec3` |

兩版都通過 signed bundle admission、Git source 比對、已安裝 wheel import、
compiled extraction 與資產檢查。一次性私鑰已刪除；公鑰 SHA256
`7323235b640d731e6f7693411817cf875bb14535ccc67e45ceb4d14c09e7196f`。
候選 unsigned，正式 Windows publisher／native-license admission 尚未通過。

`catalog.json` 只將 B 的 URL 改為本次隔離 tag，保留 B size/hash/manifest/key identity。
`A-catalog.json`／`B-catalog.json` 與 provenance 保留封裝時的原始內容。
About 與 Setup B 仍消費同一份 B bundle。

helper 是獨立驗收資產；本次增加實際 shared/update 路徑預檢，SHA256
`aa1511fadc88b1227218e840fb9e09353d293f651555e503c0f3b534eab475f8`。
從 Windows「開始」開啟一般 PowerShell 執行，避開已確認的路徑重導環境。
見 [實測步驟](../testing/github-acceptance-about-20261005.md)。

## 發布後的必要證據

匿名下載並比對 20 個檔案，重新驗證 B 簽章；由使用者保留資料移除舊 Candidate、
安裝本配對 A，再從一般 PowerShell 用隔離 helper 啟動並明確點更新。
確認 3.7.11、設定保留與原捷徑重開；reboot、故障回復、新手與乾淨 VM 各自記錄。
匿名資產下載／B 簽章已 passed；使用者實際 About、reboot、故障回復、新手與 VM 仍未通過，不能用封裝 gate 代替。

使用者已另行直接授權本次新增兩個 tag 與公開測試 Release，符合
[原始啟動要求](installer-release-readiness-prompt.md)的發布界線。

## 實際發布紀錄

- Release：[acceptance-20261005](https://github.com/yomingpan/clipai/releases/tag/acceptance-20261005)，ID `403862275`。
- 公開時間：2026-10-05 23:31:22 Asia/Taipei（`2026-10-05T15:31:22Z`）。
- `draft=false`、`prerelease=true`；正式 latest 仍 `v3.7.8`，舊 Release 的 ID、body、published_at 與全部 asset identity/hash/size 未變。
- 發布前由 GitHub 草稿畫面逐一比對 20 個名稱、SHA256 與畫面四捨五入尺寸；精確 byte 長度由發布後匿名 API 核對。
- 精確 API 證據：`artifacts/github-acceptance-publication-20261005.json`。來源 tag 未推送任何 branch，HEAD／一般 index 未變。

20 檔匿名下載完成；四個大檔以 108 個 HTTPS ranges、有限重試後重組，
逐一核對整檔 SHA256／bytes，非 About continuous-transfer 成功證據。
B 真實 Ed25519 signature admission passed。完整紀錄見
[發布證據](../evidence/github-acceptance-publication-20261005.md)。
