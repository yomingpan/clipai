# Result Output Profile Contract

Action 的輸出格式由集中式 profile 定義，避免每個 prompt 重複描述相同格式。

- `config/output_profiles.yaml` 定義 profile ID、instruction、必要 marker 與 presentation mode。
- Action 與 press variant 只引用 profile ID；config loader 在啟動時拒絕未知 profile。
- Prompt builder 將 instruction 加入 system message；provider 不讀 config 或解讀 profile。
- Result processor 執行保守驗證。缺少 marker 時記錄 warning，但保留可讀原文。
- UI、copy、paste 與 TTS 不得各自重新推測 LLM schema。

測試必須覆蓋有效引用、未知 profile、prompt 合併及格式偏差時的原文 fallback。
