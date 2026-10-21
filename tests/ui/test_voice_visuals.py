import pytest
from PIL import Image

from ClipAI.core.voice import InlineDictationView
from ClipAI.ui.voice_visuals import project_inline_visuals
from ClipAI.core.models import PasteOutcome


@pytest.mark.parametrize("phase, status", [
    ("starting", "準備麥克風…"),
    ("listening", "聆聽中…"),
    ("finalizing", "整理中…"),
    ("cancelling", "取消中…"),
    ("awaiting", "已停止 · ✓ 原文 / ✦ 潤飾"),
    ("refining", "潤飾中…"),
    ("pasting", "貼上中…"),
    ("recovery", "未完成"),
    ("cancel_unconfirmed", "取消尚未確認"),
])
def test_inline_phase_status_is_readable_without_animation(phase, status):
    assert project_inline_visuals(InlineDictationView("i", phase)).status == status


@pytest.mark.parametrize("options, border, raw, refine, spinner", [
    ({"phase": "starting"}, "#3A3D41", "#F2F2F2", "#3A3D41", None),
    ({"phase": "listening"}, "#3A3D41", "#F2F2F2", "#3A3D41", None),
    ({"phase": "finalizing"}, "#3A3D41", "#2A2B2E", "#3A3D41", "wave"),
    ({"phase": "finalizing", "chosen": "raw"}, "#3A3D41", "#2E9E5B", "#3A3D41", "raw"),
    ({"phase": "finalizing", "chosen": "refine"}, "#3A3D41", "#2A2B2E", "#6C5CE7", "refine"),
    ({"phase": "refining", "chosen": "refine"}, "#3A3D41", "#2A2B2E", "#6C5CE7", "refine"),
    ({"phase": "pasting", "chosen": "refine"}, "#3A3D41", "#2A2B2E", "#6C5CE7", "raw"),
    ({"phase": "awaiting", "allow_refine": False}, "#3A3D41", "#F2F2F2", "#2A2B2E", None),
    ({"phase": "listening", "preview_refine": True}, "#3A3D41", "#F2F2F2", "#6C5CE7", None),
    ({"phase": "listening", "countdown_seconds": 30}, "#D9A441", "#F2F2F2", "#3A3D41", None),
    ({"phase": "recovery"}, "#C0392B", "#2A2B2E", "#3A3D41", None),
    ({"phase": "settled", "paste_outcome": PasteOutcome("dispatched_unconfirmed", "dispatched_unconfirmed", "restored")}, "#2E9E5B", "#2E9E5B", "#3A3D41", None),
])
def test_visual_state_table(options, border, raw, refine, spinner):
    visual = project_inline_visuals(InlineDictationView("i", **options))
    assert (visual.border, visual.raw_fill, visual.refine_fill, visual.spinner) == (border, raw, refine, spinner)


@pytest.mark.parametrize("options, status, center", [
    ({"phase": "listening", "silence_detected": True}, "沒有收到聲音", "無聲"),
    ({"phase": "listening", "countdown_seconds": 9}, "剩 9 秒，將自動停止", "9"),
    ({"phase": "listening", "preview_refine": True}, "放開後潤飾貼上", ""),
    ({"phase": "awaiting", "allow_refine": False}, "已停止 · ✓ 原文", ""),
    ({"phase": "settled", "paste_outcome": PasteOutcome("cancelled", "not_dispatched", "not_required")}, "已取消，沒有貼上", ""),
])
def test_status_overrides_and_center_text(options, status, center):
    visual = project_inline_visuals(InlineDictationView("i", **options))
    assert (visual.status, visual.center_text) == (status, center)


@pytest.mark.parametrize("hover, allow, expected", [
    ("cancel", True, "取消 (Esc)"),
    ("refine", True, "潤飾後貼上（長按右 Alt）"),
    ("raw", True, "直接貼上（短按右 Alt）"),
    ("refine", False, "潤飾無法使用"),
])
def test_hover_status_golden(hover, allow, expected):
    assert project_inline_visuals(InlineDictationView("i", "awaiting", allow_refine=allow), hover=hover).status == expected


def test_waveform_uses_real_level_and_is_flat_when_silent_or_inactive():
    from ClipAI.ui.voice_visuals import wave_heights
    assert wave_heights(0) == (0,) * 9
    assert wave_heights(.002) == (0,) * 9
    assert wave_heights(1, listening=False) == (0,) * 9
    assert wave_heights(1, silence=True) == (0,) * 9
    assert max(wave_heights(.1)) < max(wave_heights(.8))


def test_raster_edges_blend_with_backdrop_and_keep_fully_transparent_pixels_keyed():
    from ClipAI.ui.voice_visuals import draw_pill
    background = Image.new("RGB", (132, 26), (210, 220, 230))
    bitmap = draw_pill(InlineDictationView("i", "awaiting"), backdrop=background)
    assert bitmap.size == (132, 26)
    assert bitmap.getpixel((0, 0)) == (1, 2, 3)
    assert (0, 0, 0) not in list(bitmap.getdata())
    # A rounded edge includes blended pixels, distinct from both solid fills.
    pixels = [bitmap.getpixel((x, y)) for x in range(12) for y in range(6)]
    assert any(100 < red < 210 and green > red and blue > green for red, green, blue in pixels)


@pytest.mark.parametrize("phase, allow, hint", [
    ("awaiting", True, "✓ 貼上原文 · ✦ 潤飾後貼上 · ✕ 丟棄"),
    ("awaiting", False, "✓ 貼上原文 · ✕ 丟棄"),
    ("recovery", True, "✕ 關閉"),
    ("cancel_unconfirmed", True, "Esc 重試取消"),
])
def test_panel_hint_golden(phase, allow, hint):
    assert project_inline_visuals(InlineDictationView("i", phase, allow_refine=allow)).panel_hint == hint


@pytest.mark.parametrize("options, message", [
    ({"phase": "cancel_unconfirmed"}, "取消尚未確認；不會送出貼上。可複製原文。"),
    ({"phase": "recovery"}, "尚未貼上。可複製下方內容，切回原欄位手動貼上。"),
    ({"phase": "closed", "message": "microphone unavailable"}, "microphone unavailable"),
    ({"phase": "recovery", "paste_outcome": PasteOutcome("cleanup_failed", "dispatched_unconfirmed", "failed")}, "貼上或剪貼簿還原無法確認。請檢查原欄位與剪貼簿。"),
])
def test_panel_message_golden(options, message):
    assert project_inline_visuals(InlineDictationView("i", **options)).panel_message == message


@pytest.mark.parametrize("state, label", [("idle", ""), ("pending", "複製中…"), ("succeeded", "已複製"), ("failed", "複製失敗")])
def test_copy_label_golden(state, label):
    assert project_inline_visuals(InlineDictationView("i", "recovery", copy_state=state)).copy_label == label


def test_popup_voice_capsule_shares_dark_body_and_real_wave_with_pill():
    from ClipAI.ui.voice_visuals import draw_voice_capsule
    idle = draw_voice_capsule(width=82, height=22, level=0, listening=True)
    active = draw_voice_capsule(width=82, height=22, level=.8, listening=True)
    assert idle.getpixel((41, 3)) == (30, 31, 34)
    assert idle.tobytes() != active.tobytes()
    silent = draw_voice_capsule(width=82, height=22, level=.8, listening=True, silence=True)
    assert silent.tobytes() == draw_voice_capsule(width=82, height=22, level=0, listening=True, silence=True).tobytes()
