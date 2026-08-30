# Action Language Packs

ClipAI 目前提供繁體中文與日文 Action Language Pack。它會切換 Action 名稱、prompt、feedback 文字與 output profile marker，不會切換 UI、Voice Input 語言、TTS voice、provider 或 model。

## 切換語言

1. 在 Windows 系統匣開啟 ClipAI 選單。
2. 展開 **Action Language**。
3. 選擇 **繁體中文** 或 **日本語**。
4. 等待選單顯示已儲存；若語言與目前 active pack 不同，會顯示需要重啟。
5. 完整結束並重新啟動 ClipAI。重啟前執行的 Action 仍使用原本的語言包。

選擇寫入 `data/action_language_pack.json`，只保存 schema version 與 pack ID。若所選 pack 在下次啟動時遺失、checksum 不符或不相容，ClipAI 會完整回退繁體中文並在 Tray 顯示 recovery；它不會悄悄改寫你的選擇。若繁體中文 default pack 本身無效，ClipAI 會拒絕啟動，避免混用不完整內容。

## 驗證官方語言包

在 repository root 執行：

```powershell
& .\.venv\Scripts\python.exe scripts\validate_language_packs.py
```

成功時應顯示 `validated 2 action language pack(s)`。新增或修改 pack 時，必須同步更新 manifest resource checksum，並完成 [Action Language Pack contract](contracts/services/action-language-pack-contract.md) 所列 release gate。
