from __future__ import annotations

from ClipAI.ui.tray import STATUS_COLORS, TrayController, create_tray_image


def test_tray_image_uses_requested_size_and_status_palette() -> None:
    image = create_tray_image("processing", size=32)
    assert image.size == (32, 32)
    assert STATUS_COLORS["processing"] == (255, 140, 0)


def test_tray_memory_indicator_changes_rendered_pixels() -> None:
    idle = create_tray_image("idle", memory_active=False)
    memory = create_tray_image("idle", memory_active=True)
    assert idle.tobytes() != memory.tobytes()


def test_tray_stop_cancels_pending_reset() -> None:
    tray = TrayController(lambda: None)
    tray.set_status("success")
    assert tray._reset_timer is not None
    tray.stop()
    assert tray._reset_timer is None
