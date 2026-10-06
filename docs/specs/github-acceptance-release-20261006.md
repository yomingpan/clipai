# Windows venv 修正配對發布提案：3.7.12 → 3.7.13

狀態：使用者直接授權「好發佈」；已推送兩個來源 tag 並公開為 prerelease。
遠端 20 個資產的精確 bytes／SHA256、匿名整檔下載與 B 真實簽章驗證全部通過。
目的：驗收 `identity_ineligible` 修正。原生 Windows 行程回歸及完整 unit
已通過，實際 About 更新尚未通過。

## 精確發布範圍

- Repository：`yomingpan/clipai`。
- A 來源 tag：`acceptance-20261006-a` →
  `3ac5d70d2a2c5d6d132ca868bd9a328e00b59044`，不建立另一個 Release。
- Release tag：`acceptance-20261006` →
  `b6f921ec163e50aaeb53dcac494767a3ac3d4e5a`。
- Title：`ClipAI installer/update acceptance — 3.7.12 to 3.7.13`。
- 先建立 draft、上傳完整 20 檔，逐一核對名稱、SHA256 與畫面尺寸，
  再以 `prerelease=true`、`make_latest=false` 公開。
- 公開後由匿名 API 核對精確 bytes、digest 與 uploaded 狀態，再匿名下載
  比對全部資產並驗證 B 簽章。草稿画面的四捨五入尺寸不能當精確 byte 證據。
- 保留 `acceptance-20261004`、`acceptance-20261005` 與 `v3.7.8` 的既有內容。
  不推送 branch、不改寫已安裝 keyring 或設定。

上傳目錄：`artifacts/github-acceptance-20261006/`；精確名稱／bytes／SHA256
保存於 `artifacts/about-identity-20261006/public-proposal.json`。
Release body 為資產目錄內 `release-body.md`。

| 候選 | Setup SHA256 | bundle SHA256 |
| --- | --- | --- |
| A 3.7.12 | `cc255f63b96784395f19cbc67ca07ab9da9ccc131c54e68b335675befde2aa8b` | `5e81414093b08485e93e9f046cbc4810abe22f32f0e58e01661be19d46b8071d` |
| B 3.7.13 | `dcbe56d50864f87b241d7fcf7069963ea1d6b884153557392cfc550d2b8dbcb2` | `ffeb63a0d234b4f62362433f1326fc0722d85342c4d56912389f0218887a4153` |

兩版均通過 signed bundle admission、精確 Git source 比對、已安裝 wheel
import、compiled extraction 與資產檢查。一次性私鑰已刪除；公鑰 SHA256
`fb01bca9912bdcf57eceb8b201789cb58dbdf9a943e721beb6b60cdbfa281d33`。
helper SHA256 `aa1511fadc88b1227218e840fb9e09353d293f651555e503c0f3b534eab475f8`。
HEAD 與一般 index 未變；上述兩個來源 tag 已推送，不推送 branch。

## 驗證與限制

完整 managed-bundle gate 通過：1,964 unit、synthetic 1、真實 HTTPS／signature 2、
signed managed-bundle 2。最後 host 錯誤投影修正後，13 targeted 與完整
1,966 unit 通過；原生 Windows venv／同 PID handle 正常退出另有 1 integration 通過。

兩版包含 stable launcher 的身分驗證修正。Windows adapter 只允許明確指定的
base runtime 與該版 venv 的 contained `home` 對應；host 先證明既有 signed
logical install，再開啟行程 handle。外來 runtime／home 仍被拒絕。

Setup B 與 About 使用同一份 B bundle。原始 A/B catalog 與 provenance 保留；
公開 `catalog.json` 僅改 B URL 為本次隔離 tag。新配對與舊配對 trust authority
不同，需保留資料移除舊 Candidate，再安裝新 A，不手動替換 keyring。

候選無 Windows publisher 簽章；正式發行 NO-GO。實際 About、reboot、
故障回復、新手、乾淨 VM 與正式簽署檔驗收仍未通過。
見 [診斷證據](../evidence/about-identity-ineligible-20261006.md)、
[人工實測步驟](../testing/github-acceptance-about-20261006.md)。

使用者直接授權本次精確配對，符合
[原始啟動要求](installer-release-readiness-prompt.md)的發布界線。

## 實際發布紀錄

[Release acceptance-20261006](https://github.com/yomingpan/clipai/releases/tag/acceptance-20261006)，
ID `404200744`，2026-10-06 08:52:13 Asia/Taipei 公開。
`draft=false`、`prerelease=true`；正式 latest 仍 `v3.7.8`。
20 個遠端資產的精確名稱／bytes／SHA256／uploaded state 及 body／title 都 passed。
20 檔匿名下載／整檔 SHA256 與 B Ed25519 admission 都 passed；大檔有界 ranges／重試
不是使用者 About 的單次連續下載或交接成功證據。
舊兩個 acceptance releases 與 latest 的 immutable identities 保持相同。
見[完整發布證據](../evidence/github-acceptance-publication-20261006.md)。
