# 交接期限修正候選發布：2026-10-06 r2

使用者直接授權：「重新建置並發布 我會等待你結束後 再測試一次」。
發布目的：讓另一台電腦重測 App 20 秒放棄、host 78 秒才 ready 的修正。

- A：3.7.14，source `abe4eb06349011be63bb0ddee0766bc87b871004`。
- B：3.7.15，source `35d5ec828e1a237f5280eda6e98fff5d11076a02`。
- 來源差異只有 `pyproject.toml` 版本；兩版都含 600 秒準備等待與截止取樣修正。
- 新 tags：`acceptance-20261006-r2-a`／`acceptance-20261006-r2`。
- 新 GitHub prerelease：`acceptance-20261006-r2`；20 個精確公開資產。
- 同一 tag、來源 commit 與 bundle：B Setup 內含與 About catalog 指向同一份 B bundle。
- A／B 使用同一配對 Ed25519 authority；一次性私鑰不發布並在建置後移除。
- Setup 是既有 unsigned technical candidate，正式 Windows publisher gate 保持未通過。
- 舊 tags／Release／production latest 保持原 identity；不修改使用者安裝或設定。

建置紀錄與精確 hash proposal：`artifacts/about-handoff-timeout-20261006/`。
最終資產：`artifacts/github-acceptance-20261006-r2/`。
發布前完成來源與封裝一致性、離線 installed import、Setup extraction、資產 admission；
發布後核對匿名 API 精確資產、catalog discovery、下載 SHA256 與 B signature admission。

[人工實測步驟](../testing/github-acceptance-about-20261006-r2.md)。
