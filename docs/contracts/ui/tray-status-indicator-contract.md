# Tray Status Indicator Contract

Tray 使用 ClipAI 雙斜線 logo 與一致燈號，提供低干擾的 application status 回饋。

- Core 只定義 `ApplicationStatus` 與 `StatusIndicator` port。
- Tray 是 UI adapter，由 composition root 注入；禁止 provider 或 global Event Bus 更新 tray。
- 工作中為橘色；完成為綠色 2 秒；失敗為紅色 3 秒；取消、關閉與無工作為藍色。
- Tray adapter 負責 thread、icon lock、retry、reset timer 與 stop cleanup。
- `memory_active` 預留在 port；沒有 memory service 時固定 false。

Icon renderer、status mapping、memory pixel difference 與 timer cleanup 必須可在不啟動真實 tray 下測試。
