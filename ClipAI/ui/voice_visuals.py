"""Shared, widget-neutral Voice drawing and presentation vocabulary."""

from dataclasses import dataclass
from functools import lru_cache
import math

from PIL import Image, ImageDraw, ImageFilter

from ClipAI.core.voice import InlineDictationView, VoiceTransportFailure

TRANSPARENT_KEY = "#010203"
BODY = "#1E1F22"
BUTTON = OUTLINE = "#3A3D41"
DISABLED = "#2A2B2E"
AMBER = "#D9A441"
RED = "#C0392B"
GREEN = "#2E9E5B"
REFINE = "#6C5CE7"
CONFIRM = "#F2F2F2"
MUTED = "#7A7D82"
WHITE = "#FFFFFF"
SILENCE_WORD = "無聲"
SUPERSAMPLE = 4
BASE_WIDTH = 160
BASE_HEIGHT = 36
STRIP_HEIGHT = 18
CANVAS_WIDTH = 300
PANEL_HEIGHT = 136
CANVAS_HEIGHT = PANEL_HEIGHT + STRIP_HEIGHT + BASE_HEIGHT
PANEL_RADIUS = 10
HIT_PADDING = 3
REFINE_DIAMETER = 24
BUTTON_CENTERS = (("cancel", 18), ("refine", 110), ("raw", 142))
CENTER_Y = BASE_HEIGHT / 2
WAVE_LEFT = 43
WAVE_WIDTH = 41
WAVE_CENTER = WAVE_LEFT + WAVE_WIDTH / 2
SHELL_OUTLINE = "#737977"
BUTTON_RIM = "#4B5050"
REFINE_ACTIVE = "#414447"
REFINE_LIGHT = "#D1C9E7"
REFINE_RING_FRAMES = 20
WAVE_BARS = 9
FRAME_MS = 80
MARGIN = 8
MESSAGE_COLOR = "#B8C9C3"


@dataclass(frozen=True)
class InlineVisuals:
    status: str
    border: str = OUTLINE
    raw_fill: str = DISABLED
    refine_fill: str = BUTTON
    spinner: str | None = None
    center_text: str = ""
    panel_message: str = ""
    copy_label: str = ""
    panel_title: str = ""
    panel_copy: bool = False


def _notice_card(view: InlineDictationView) -> tuple[str, str]:
    """Present typed owner facts, never parse or expose diagnostic prose."""
    if view.phase == "cancel_unconfirmed":
        return "取消仍在確認", "尚未送出貼上。內容已保留，可先複製；Esc 可重試取消。"
    if view.phase == "recovery":
        if view.paste_outcome is None:
            return "找不到原輸入欄", "內容已保留。複製後，切回要輸入的位置手動貼上。"
        if view.paste_outcome.state == "cleanup_failed":
            return "貼上狀態需要確認", "請先檢查原輸入欄與剪貼簿，再決定是否手動貼上。內容仍可複製。"
        return "尚未貼上", "內容已保留。可複製後，切回原輸入欄手動貼上。"
    if view.phase not in {"awaiting", "closed"}:
        return "", ""
    if view.phase == "closed" and not view.message:
        return "", ""
    if view.phase == "awaiting" and not view.allow_refine:
        return "潤飾未完成", "原文已保留。短按右 Alt 貼上原文，或先複製內容。"
    notice = view.capture_notice
    if notice == "cancel_timeout":
        return "取消等待逾時", "未送出貼上。麥克風停止狀態未能確認，請檢查語音服務後再試。"
    titles = {
        "no_speech": "沒有辨識到語音", "time_limit": "已達錄音時間上限",
        "missing_segment": "部分語音未能辨識",
        VoiceTransportFailure.PERMISSION_DENIED: "需要麥克風權限",
        VoiceTransportFailure.PERMISSION_BLOCKED: "麥克風權限遭封鎖",
        VoiceTransportFailure.UNAVAILABLE: "語音服務無法使用",
        VoiceTransportFailure.INITIALIZATION_FAILED: "麥克風未能啟動",
        VoiceTransportFailure.PROCESS_CRASHED: "語音辨識意外中斷",
        VoiceTransportFailure.PROTOCOL_ERROR: "語音辨識回應異常",
        VoiceTransportFailure.TIMEOUT: "語音辨識等待逾時",
        VoiceTransportFailure.CANCELLED: "語音輸入已取消",
    }
    if notice is not None:
        title = titles[notice]
        if view.text:
            return title, "已保留辨識到的文字。可貼上原文或複製內容；使用前請確認內容是否完整。"
        if notice in {VoiceTransportFailure.PERMISSION_DENIED, VoiceTransportFailure.PERMISSION_BLOCKED}:
            return title, "請在系統或語音服務設定中允許麥克風，再重新開始。"
        if notice == VoiceTransportFailure.UNAVAILABLE:
            return title, "未送出貼上。請檢查連線與語音設定後再試。"
        return title, "這次沒有可送出的文字，請重新開始。"
    if view.phase == "closed":
        return "語音輸入未完成", "未送出貼上，請重新開始。"
    return "辨識完成", "短按右 Alt 貼上原文，長按可潤飾後貼上。"


def project_inline_visuals(view: InlineDictationView, *, hover: str = "") -> InlineVisuals:
    status = {
        "starting": "準備麥克風…",
        "listening": "聆聽中…",
        "finalizing": "整理中…",
        "cancelling": "取消中…",
        "awaiting": "已停止 · ✓ 原文 / ✦ 潤飾",
        "refining": "潤飾中…",
        "pasting": "貼上中…",
        "recovery": "未完成",
        "cancel_unconfirmed": "取消尚未確認",
        "closed": "未完成" if view.message else "已取消，沒有貼上",
        "settled": "已送出貼上，請確認原欄位",
    }[view.phase]
    cancelled = view.paste_outcome is not None and view.paste_outcome.state == "cancelled"
    done = view.paste_outcome is not None and view.paste_outcome.state == "dispatched_unconfirmed"
    failed = view.phase == "recovery" or view.phase == "closed" and bool(view.message)
    countdown = view.countdown_seconds if view.phase == "listening" else None
    countdown = countdown if countdown is not None and countdown <= 30 else None
    clickable = view.phase in {"starting", "listening", "awaiting"}
    center = ""
    if cancelled:
        status = "已取消，沒有貼上"
    if view.phase == "awaiting" and not view.allow_refine:
        status = "已停止 · ✓ 原文"
    if view.phase == "listening" and view.silence_detected:
        status, center = "沒有收到聲音", SILENCE_WORD
    if countdown is not None:
        status, center = f"剩 {countdown} 秒，將自動停止", str(countdown)
    if view.preview_refine:
        status = "放開後潤飾貼上"
    status = {
        "cancel": "取消 (Esc)",
        "raw": "直接貼上（短按右 Alt）",
        "refine": "潤飾後貼上（長按右 Alt）" if view.allow_refine else "潤飾無法使用",
    }.get(hover, status)
    spinner = (
        "refine" if view.phase == "refining" else
        "raw" if view.phase == "pasting" else
        view.chosen or "wave" if view.phase == "finalizing" else None
    )
    panel_title, panel_message = _notice_card(view)
    return InlineVisuals(
        status, RED if failed else GREEN if done else AMBER if countdown is not None else OUTLINE,
        GREEN if view.chosen == "raw" or done else CONFIRM if clickable else DISABLED,
        DISABLED if not view.allow_refine else REFINE if view.chosen == "refine" or view.preview_refine else BUTTON,
        spinner, center, panel_message,
        {"idle": "", "pending": "複製中…", "succeeded": "已複製", "failed": "複製失敗"}[view.copy_state],
        panel_title, bool(view.text) and view.phase != "closed" and bool(panel_title),
    )


def wave_heights(level: float, *, frame: int = 0, listening: bool = True, silence: bool = False) -> tuple[float, ...]:
    level = max(0.0, min(1.0, level)) if listening and not silence else 0.0
    if level <= .002:
        return (0.0,) * WAVE_BARS
    return tuple(
        level * 7 * (.35 + .65 * abs(math.sin(index * .8 + frame * .42)))
        for index in range(WAVE_BARS)
    )


def composite_backdrop(layer: Image.Image, backdrop: Image.Image | None) -> Image.Image:
    """Opaque antialiased edges use the pre-show backdrop, never the color key."""
    background = backdrop.convert("RGBA") if backdrop is not None else Image.new("RGBA", layer.size, BODY)
    if background.size != layer.size:
        raise ValueError("backdrop dimensions must match the raster")
    composed = Image.alpha_composite(background, layer).convert("RGB")
    alpha = layer.getchannel("A")
    fully_transparent = alpha.point(lambda value: 255 if value == 0 else 0)
    composed.paste(TRANSPARENT_KEY, mask=fully_transparent)
    return composed


def _line(draw: ImageDraw.ImageDraw, points: list[tuple[float, float]], color: str, width: float) -> None:
    draw.line(points, fill=color, width=max(1, round(width)), joint="curve")
    radius = width / 2
    for x, y in (points[0], points[-1]):
        draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=color)


def _icon(draw: ImageDraw.ImageDraw, kind: str, cx: float, cy: float, unit: float, color: str) -> None:
    if kind == "cancel":
        for sign in (-1, 1):
            _line(draw, [(cx-3*unit, cy-sign*3*unit), (cx+3*unit, cy+sign*3*unit)], color, 1.5*unit)
    elif kind == "raw":
        _line(draw, [(cx-4*unit, cy), (cx-unit, cy+3*unit), (cx+4*unit, cy-3*unit)], color, 1.6*unit)
    else:
        points = []
        for index in range(8):
            angle = index * math.pi / 4 - math.pi / 2
            radius = (5 if index % 2 == 0 else 1.6) * unit
            points.append((cx+math.cos(angle)*radius, cy+math.sin(angle)*radius))
        draw.polygon(points, fill=color)


def _spinner(draw: ImageDraw.ImageDraw, cx: float, cy: float, unit: float, frame: int, color: str) -> None:
    radius = 5 * unit
    draw.arc((cx-radius, cy-radius, cx+radius, cy+radius), start=frame*32, end=frame*32+250, fill=color, width=max(1, round(1.5*unit)))


def _wave(draw: ImageDraw.ImageDraw, left: float, cy: float, width: float, unit: float, heights: tuple[float, ...], color: str) -> None:
    for index, height in enumerate(heights):
        x = left + index * width / (WAVE_BARS-1)
        half = max(.35, height) * unit
        _line(draw, [(x, cy-half), (x, cy+half)], color, 1.5*unit)


def _blend(first: str, second: str, amount: float) -> tuple[int, int, int]:
    return tuple(round(int(first[i:i+2], 16)*(1-amount) + int(second[i:i+2], 16)*amount) for i in (1, 3, 5))


@lru_cache(maxsize=1)
def _button_perimeter() -> tuple[tuple[float, float], ...]:
    """Uniform-distance clockwise samples on the circular button border."""
    radius = REFINE_DIAMETER/2-.75
    return tuple(
        (radius*math.cos(index*2*math.pi/160-math.pi/2),
         radius*math.sin(index*2*math.pi/160-math.pi/2))
        for index in range(160)
    )


def _refine_ring(draw, cx, cy, unit, frame, fill):
    points = _button_perimeter()
    head = (frame % REFINE_RING_FRAMES)*len(points)//REFINE_RING_FRAMES
    length = len(points)//4
    for step in range(length):
        start = points[(head-length+step) % len(points)]
        end = points[(head-length+step+1) % len(points)]
        color = _blend(fill, REFINE_LIGHT, (step+1)/length)
        draw.line([(cx+start[0]*unit, cy+start[1]*unit), (cx+end[0]*unit, cy+end[1]*unit)], fill=color, width=max(1, round(1.5*unit)))


def _pill_layer(scale, border, refine_fill, raw_fill, spinner, heights, wave_color, allow_refine, frame, hover):
    size = (round(BASE_WIDTH*scale), round(BASE_HEIGHT*scale))
    unit = scale * SUPERSAMPLE
    layer = Image.new("RGBA", (size[0]*SUPERSAMPLE, size[1]*SUPERSAMPLE))
    draw = ImageDraw.Draw(layer)
    draw.rounded_rectangle((0, 0, layer.width-1, layer.height-1), radius=CENTER_Y*unit, fill=BODY, outline=SHELL_OUTLINE if border == OUTLINE else border, width=max(1, round(unit)))
    centers = dict(BUTTON_CENTERS)
    for kind, cx, fill, foreground in (
        ("cancel", centers["cancel"], BUTTON, CONFIRM),
        ("refine", centers["refine"], REFINE_ACTIVE if refine_fill == REFINE else refine_fill, MUTED if not allow_refine else WHITE if refine_fill == REFINE else CONFIRM),
        ("raw", centers["raw"], raw_fill, WHITE if raw_fill == GREEN else BODY if raw_fill == CONFIRM else MUTED),
    ):
        radius = REFINE_DIAMETER/2 * unit
        button_fill = _blend(fill, WHITE, .07) if hover == kind else fill
        bounds = ((cx*unit)-radius, CENTER_Y*unit-radius, (cx*unit)+radius, CENTER_Y*unit+radius)
        draw.ellipse(bounds, fill=button_fill)
        if kind != "raw" and (kind != "refine" or allow_refine):
            draw.ellipse(bounds, outline=BUTTON_RIM, width=max(1, round(.5*unit)))
        if kind == "refine" and allow_refine:
            # A stationary, restrained halo belongs to the glyph, not a timer.
            glow = Image.new("RGBA", (round(2*radius)+1, round(2*radius)+1))
            _icon(ImageDraw.Draw(glow), kind, radius, radius, unit, WHITE)
            glow = glow.filter(ImageFilter.GaussianBlur(1.3*unit))
            glow.putalpha(glow.getchannel("A").point(lambda alpha: round(alpha*.18)))
            layer.alpha_composite(glow, (round(cx*unit-radius), round(CENTER_Y*unit-radius)))
        if spinner == kind and kind != "refine":
            _spinner(draw, cx*unit, CENTER_Y*unit, unit, frame, foreground)
        else:
            _icon(draw, kind, cx*unit, CENTER_Y*unit, unit, foreground)
        if spinner == kind == "refine":
            # The glyph stays still; only the perimeter conveys pending work.
            _refine_ring(draw, cx*unit, CENTER_Y*unit, unit, frame, fill)
    if spinner == "wave":
        _spinner(draw, WAVE_CENTER*unit, CENTER_Y*unit, unit, frame, CONFIRM)
    else:
        _wave(draw, WAVE_LEFT*unit, CENTER_Y*unit, WAVE_WIDTH*unit, unit, heights, wave_color)
    return layer.resize(size, Image.Resampling.LANCZOS)


# Cache only bounded, content-free static geometry. Background pixels and
# interaction/view identities never enter this cache; animation stays uncached.
_static_pill_layer = lru_cache(maxsize=16)(_pill_layer)


def draw_pill(view: InlineDictationView, *, scale: float = 1.0, frame: int = 0, backdrop: Image.Image | None = None, hover: str = "") -> Image.Image:
    visual = project_inline_visuals(view)
    heights = wave_heights(view.audio_level, frame=frame, listening=view.phase == "listening", silence=view.silence_detected)
    wave_color = MUTED if view.phase in {"starting", "cancelling"} or view.silence_detected else WHITE
    animated = visual.spinner is not None or any(heights)
    render = _pill_layer if animated else _static_pill_layer
    interactive_hover = hover if view.phase in {"starting", "listening", "awaiting"} and (hover != "refine" or view.allow_refine) else ""
    refine_active = view.allow_refine and (view.phase in {"starting", "listening", "awaiting"} or visual.spinner == "refine")
    layer = render(scale, visual.border, visual.refine_fill, visual.raw_fill, visual.spinner, heights, wave_color, refine_active, frame if animated else 0, interactive_hover)
    return composite_backdrop(layer, backdrop)


def draw_panel(*, scale: float = 1, backdrop: Image.Image | None = None) -> Image.Image:
    size = (round(CANVAS_WIDTH*scale), round(PANEL_HEIGHT*scale))
    layer = Image.new("RGBA", (size[0]*SUPERSAMPLE, size[1]*SUPERSAMPLE))
    ImageDraw.Draw(layer).rounded_rectangle((0, 0, layer.width-1, layer.height-1), radius=PANEL_RADIUS*scale*SUPERSAMPLE, fill=BODY)
    return composite_backdrop(layer.resize(size, Image.Resampling.LANCZOS), backdrop)


def draw_voice_capsule(
    *, width: int, height: int, level: float, listening: bool,
    silence: bool = False, finishing: bool = False, enabled: bool = True,
    countdown: bool = False, frame: int = 0, scale: float = 1,
    wave_width: float | None = None, background: str = BODY,
) -> Image.Image:
    unit = scale*SUPERSAMPLE
    layer = Image.new("RGBA", (width*SUPERSAMPLE, height*SUPERSAMPLE))
    draw = ImageDraw.Draw(layer)
    draw.rounded_rectangle((0, 0, layer.width-1, layer.height-1), radius=9*unit, fill=BODY, outline=AMBER if countdown else OUTLINE, width=max(1, round(unit)))
    area = wave_width if wave_width is not None else width/scale-14
    if finishing:
        _spinner(draw, (7+area/2)*unit, layer.height/2, unit, frame, CONFIRM)
    else:
        _wave(draw, 7*unit, layer.height/2, area*unit, unit, wave_heights(level, frame=frame, listening=listening and enabled, silence=silence), MUTED if silence or not enabled else WHITE)
    layer = layer.resize((width, height), Image.Resampling.LANCZOS)
    return Image.alpha_composite(Image.new("RGBA", layer.size, background), layer).convert("RGB")
