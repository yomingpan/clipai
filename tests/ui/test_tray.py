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


def test_tray_status_is_a_dumb_projection_without_reset_timer() -> None:
    tray = TrayController(lambda: None)
    tray.set_status("success")
    assert tray._status == "success"
    tray.stop()


def test_tray_keeps_diagnostics_callback_separate_from_export_work() -> None:
    events: list[str] = []
    tray = TrayController(lambda: None, lambda: events.append("export"))
    assert tray._on_export_diagnostics is not None
    tray._on_export_diagnostics()
    assert events == ["export"]
