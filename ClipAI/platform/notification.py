
try:
    from plyer import notification
except ImportError:
    notification = None

# Global flag to enable/disable notifications
enabled = False

def notify(title, message):
    """Send a Windows toast notification."""
    if not enabled:
        return

    if notification:
        try:
            notification.notify(
                title=title,
                message=message,
                app_name="ClipAI",
                timeout=3,  # Seconds
            )
        except Exception as e:
            print(f"[clipai] Notification failed: {e}")
    else:
        print(f"[clipai] {title}: {message}")


