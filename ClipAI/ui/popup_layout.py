from __future__ import annotations

from ClipAI.core.models import DisplayMetrics, PopupBounds


class PopupLayoutPolicy:
    # Reading-first baseline: compact chrome preserves space for result content.
    DEFAULT_WIDTH = 400
    DEFAULT_HEIGHT = 320
    MIN_WIDTH = 340
    MIN_HEIGHT = 220
    MARGIN = 16

    def calculate(self, metrics: DisplayMetrics, *, content_lines: int = 8) -> PopupBounds:
        scale = max(metrics.scale, 0.5)
        del content_lines
        max_width = int(metrics.work_width / scale * 0.60)
        max_height = int(metrics.work_height / scale * 0.70)
        width = min(max_width, max(self.DEFAULT_WIDTH, self.MIN_WIDTH))
        height = min(max_height, max(self.DEFAULT_HEIGHT, self.MIN_HEIGHT))
        margin = int(self.MARGIN * scale)
        physical_width = int(width * scale)
        physical_height = int(height * scale)
        x = metrics.cursor_x - physical_width // 3
        y = metrics.cursor_y - physical_height // 4
        x = max(metrics.work_x + margin, min(x, metrics.work_x + metrics.work_width - physical_width - margin))
        y = max(metrics.work_y + margin, min(y, metrics.work_y + metrics.work_height - physical_height - margin))
        return PopupBounds(x, y, width, height)
