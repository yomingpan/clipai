from __future__ import annotations

from plyer import notification as plyer_notification


def notify(title: str, message: str) -> None:
    plyer_notification.notify(title=title, message=message)
