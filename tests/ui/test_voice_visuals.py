import pytest
from PIL import Image, ImageChops

from ClipAI.core.voice import InlineDictationView
from ClipAI.ui.voice_visuals import project_inline_visuals
from ClipAI.core.models import PasteOutcome
from ClipAI.core.voice import VoiceTransportFailure


@pytest.mark.parametrize("reason", [*VoiceTransportFailure, "no_speech", "time_limit", "missing_segment", "cancel_timeout"])
@pytest.mark.parametrize("partial", [False, True])
def test_every_capture_notice_has_short_localized_feedback_without_diagnostics_or_transcript(reason, partial):
    view = InlineDictationView("i", "awaiting" if partial else "closed", text="private recognized content" if partial else "", message="unbounded provider diagnostic "*100, capture_notice=reason)
    visual = project_inline_visuals(view)
    assert visual.panel_title and visual.panel_message
    assert len(visual.panel_title) <= 20 and len(visual.panel_message) <= 70
    assert "diagnostic" not in visual.panel_message
    assert "private recognized content" not in visual.panel_message
    assert visual.panel_copy == partial


@pytest.mark.parametrize("scale", [1, 1.25, 1.5, 1.75, 2])
def test_shell_has_one_uniform_stroke_without_a_brighter_overlaid_top_bar(scale):
    from ClipAI.ui.voice_visuals import draw_pill
    bitmap = draw_pill(InlineDictationView("i"), scale=scale)
    top = bitmap.crop((round(25*scale), 0, round(135*scale), round(3*scale)))
    # LANCZOS may overshoot the gray by a few levels at fractional DPI.
    assert all(max(pixel) <= 132 for pixel in top.getdata())


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
    background = Image.new("RGB", (160, 36), (210, 220, 230))
    bitmap = draw_pill(InlineDictationView("i", "awaiting"), backdrop=background)
    assert bitmap.size == (160, 36)
    assert bitmap.getpixel((0, 0)) == (1, 2, 3)
    assert (0, 0, 0) not in list(bitmap.getdata())
    # A rounded edge includes blended pixels, distinct from both solid fills.
    pixels = [bitmap.getpixel((x, y)) for x in range(12) for y in range(6)]
    assert any(100 < red < 210 and green > red and blue > green for red, green, blue in pixels)


@pytest.mark.parametrize("phase, allow, title", [
    ("awaiting", True, "辨識完成"),
    ("awaiting", False, "潤飾未完成"),
    ("recovery", True, "找不到原輸入欄"),
    ("cancel_unconfirmed", True, "取消仍在確認"),
])
def test_notification_title_golden(phase, allow, title):
    assert project_inline_visuals(InlineDictationView("i", phase, allow_refine=allow)).panel_title == title


@pytest.mark.parametrize("options, message", [
    ({"phase": "cancel_unconfirmed"}, "尚未送出貼上。內容已保留，可先複製；Esc 可重試取消。"),
    ({"phase": "recovery"}, "內容已保留。複製後，切回要輸入的位置手動貼上。"),
    ({"phase": "closed", "message": "microphone unavailable"}, "未送出貼上，請重新開始。"),
    ({"phase": "recovery", "paste_outcome": PasteOutcome("cleanup_failed", "dispatched_unconfirmed", "failed")}, "請先檢查原輸入欄與剪貼簿，再決定是否手動貼上。內容仍可複製。"),
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


@pytest.mark.parametrize("scale", [1, 1.25, 1.5, 1.75, 2])
def test_refine_light_moves_only_around_button_perimeter_and_loops_in_1600ms(scale):
    from ClipAI.ui.voice_visuals import draw_pill, FRAME_MS, REFINE_RING_FRAMES
    view = InlineDictationView("i", "refining", chosen="refine")
    first = draw_pill(view, scale=scale, frame=0)
    quarter = draw_pill(view, scale=scale, frame=5)
    assert first.size == (round(160*scale), round(36*scale))
    assert FRAME_MS*REFINE_RING_FRAMES == 1600
    assert first.tobytes() == draw_pill(view, scale=scale, frame=REFINE_RING_FRAMES).tobytes()
    difference = ImageChops.difference(first, quarter)
    assert difference.getbbox() is not None
    # The sparkle, its surrounding center, and every other control stay still.
    center = tuple(round(value*scale) for value in (104, 12, 116, 24))
    assert difference.crop(center).getbbox() is None
    bounds = difference.getbbox()
    assert bounds[0] >= round(95*scale) and bounds[2] <= round(125*scale)
    assert bounds[1] >= round(3*scale) and bounds[3] <= round(33*scale)
    # Once provider work ends, the refine perimeter stops animating.
    pasting = InlineDictationView("i", "pasting", chosen="refine")
    box = tuple(round(value*scale) for value in (95, 3, 125, 33))
    assert draw_pill(pasting, scale=scale, frame=0).crop(box).tobytes() == draw_pill(pasting, scale=scale, frame=5).crop(box).tobytes()


def test_hover_changes_only_the_enabled_button_without_moving_its_glyph():
    from ClipAI.ui.voice_visuals import draw_pill
    view = InlineDictationView("i", "awaiting")
    difference = ImageChops.difference(draw_pill(view), draw_pill(view, hover="refine"))
    assert difference.getbbox() is not None
    left, top, right, bottom = difference.getbbox()
    assert 95 <= left < right <= 125 and 3 <= top < bottom <= 33
    assert difference.getpixel((110, 18)) == (0, 0, 0)
    disabled = InlineDictationView("i", "awaiting", allow_refine=False)
    assert draw_pill(disabled).tobytes() == draw_pill(disabled, hover="refine").tobytes()


@pytest.mark.parametrize("center, fill", [(18, (58, 61, 65)), (110, (58, 61, 65)), (142, (242, 242, 242))])
def test_reference_style_uses_circular_gray_controls_and_white_confirm(center, fill):
    from ClipAI.ui.voice_visuals import draw_pill
    bitmap = draw_pill(InlineDictationView("i", "awaiting"), scale=3)
    assert bitmap.getpixel((center*3, 10*3)) == fill
    # A circle leaves its diagonal corners open; a rounded square fills them.
    corner = bitmap.getpixel(((center-9)*3, 9*3))
    assert max(corner) < 45


def test_refining_keeps_gray_fill_and_only_the_perimeter_gets_a_color_accent():
    from ClipAI.ui.voice_visuals import draw_pill
    bitmap = draw_pill(InlineDictationView("i", "refining", chosen="refine"), scale=3)
    red, green, blue = bitmap.getpixel((110*3, 10*3))
    assert max(red, green, blue)-min(red, green, blue) < 12
