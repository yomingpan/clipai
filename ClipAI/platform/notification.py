from __future__ import annotations

import logging


logger = logging.getLogger("clipai.notification")


class SystemNotifier:
    def notify(self, title: str, message: str) -> None:
        try:
            from plyer import notification

            notification.notify(app_name="ClipAI", title=title, message=message, timeout=6)
        except Exception:
            logger.exception("Desktop notification failed title=%s", title)
