from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
import sys
from dataclasses import dataclass
from typing import Callable, Literal, Mapping, Protocol

import customtkinter as ctk

from ClipAI.core.models import ActionFeedbackContract, FeedbackOperationState, FeedbackOutcome, PresentationDocument

from ClipAI.ui.dialog_lifecycle import DialogLifecycle
from ClipAI.ui.text_layout import DISPLAY_BREAK_HINT, add_display_break_hints, display_break_opportunity, strip_display_break_hints

DialogState = Literal["idle", "success", "error", "warning"]
ResultActionId = Literal["speaker", "copy", "paste", "archive", "follow_up"]
SOURCE_PREVIEW_MAX_CHARS = 36
DISPLAY_BREAK_TAG = "display_break_hint"


class _TextInserter(Protocol):
    def insert(self, index: str, text: str, tags: tuple[str, ...]) -> object: ...


def ellipsize_source_preview(text: str, limit: int = SOURCE_PREVIEW_MAX_CHARS) -> str:
    """Project source context onto one compact line without changing canonical content."""
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    if limit <= 3:
        return "." * max(limit, 0)
    return f"{compact[: limit - 3].rstrip()}..."


def action_contract_tooltip_text(contract: ActionFeedbackContract) -> str:
    return (
        f"AI 幫你\n{contract.transform_label}\n\n"
        f"你仍保留\n{contract.human_space_label}\n\n"
        f"結果後確認\n{contract.verification_label}\n\n"
        "Ctrl + R：Recipe 回饋"
    )


RGB = tuple[int, int, int]

DEFAULT_STATE_COLORS: dict[DialogState, RGB] = {
    "idle": (0, 119, 200),
    "success": (0, 176, 79),
    "error": (232, 17, 35),
    "warning": (255, 215, 0),
}

SURFACE_BG = "#2B2B2B"
ACTION_COLOR = "#1F6AA5"
ACTION_HOVER_COLOR = "#2879B8"
SPEAKER_ACTIVE_COLOR = "#7F1D1D"
SPEAKER_ACTIVE_HOVER_COLOR = "#991B1B"
FOLLOW_ACTIVE_COLOR = "#305B9C"
ANALYZING_COLOR = "#707070"
MODEL_COLOR = "#6E6C69"
CONTENT_COLOR = "#D8E0E8"
TC_FONT_FAMILY = "Microsoft JhengHei UI"
ACTION_ICON_FONT_FAMILY = "Segoe MDL2 Assets"
POPUP_FONT_SIZES: Mapping[str, int] = {
    "auxiliary": 11,
    "model": 9,
    "interface": 12,
    "content": 14,
    "heading_3": 15,
    "heading_2": 16,
    "heading_1": 18,
    "tooltip": 12,
}
SPEAKER_ICON = "\uE767"
STOP_ICON = "\uE71A"
COPY_ICON = "\uE77F"
PASTE_ICON = "↪"
ARCHIVE_ICON = "▣"
FOLLOW_UP_ICON = "\uE8BD"
CHECK_ICON = "\uE73E"
PIN_ICON = "\uE718"
UNPIN_ICON = "\uE77A"

PRESENTATION_TAG_STYLES: dict[str, dict[str, object]] = {
    "heading_1": {"foreground": "#8EC5FF", "spacing1": 10, "spacing3": 6},
    "heading_2": {"foreground": "#A9D4FF", "spacing1": 9, "spacing3": 5},
    "heading_3": {"foreground": "#C5E2FF", "spacing1": 8, "spacing3": 4},
    "bold": {"foreground": "#FFFFFF"},
    "italic": {"foreground": "#AFC0D2"},
    "paragraph": {"spacing3": 10},
    "list": {"spacing1": 1, "spacing3": 4},
}
TITLE_COLOR = PRESENTATION_TAG_STYLES["heading_1"]["foreground"]

PRESENTATION_TAG_FONTS: dict[str, tuple[str, int, str]] = {
    "heading_1": (TC_FONT_FAMILY, POPUP_FONT_SIZES["heading_1"], "bold"),
    "heading_2": (TC_FONT_FAMILY, POPUP_FONT_SIZES["heading_2"], "bold"),
    "heading_3": (TC_FONT_FAMILY, POPUP_FONT_SIZES["heading_3"], "bold"),
    "bold": (TC_FONT_FAMILY, POPUP_FONT_SIZES["content"], "bold"),
    "italic": (TC_FONT_FAMILY, POPUP_FONT_SIZES["content"], "italic"),
}


def apply_widget_font_scaling(widget: object, font: tuple[str, int] | tuple[str, int, str]) -> tuple:
    """Apply CustomTkinter's owning-widget font scale before crossing into Tk."""
    apply_scaling = getattr(widget, "_apply_font_scaling", None)
    if not callable(apply_scaling):
        raise AttributeError("widget does not expose CustomTkinter font scaling")
    scaled = apply_scaling(font)
    if len(scaled) == 3 and isinstance(scaled[2], tuple):
        return (*scaled[:2], *scaled[2])
    return scaled


def configure_presentation_typography(textbox: object) -> bool:
    """Apply font variants at the concrete Tk adapter seam."""
    tk_text = getattr(textbox, "_textbox", None)
    if tk_text is None or not hasattr(tk_text, "tag_configure"):
        return False
    try:
        for tag, font in PRESENTATION_TAG_FONTS.items():
            tk_text.tag_configure(tag, font=apply_widget_font_scaling(textbox, font))
    except (tk.TclError, ValueError, AttributeError):
        return False
    return True


def configure_display_break_typography(textbox: object) -> bool:
    """Keep Tk-recognized ASCII break spaces visually negligible."""
    tk_text = getattr(textbox, "_textbox", None)
    if tk_text is None or not hasattr(tk_text, "tag_configure"):
        return False
    try:
        tk_text.tag_configure(DISPLAY_BREAK_TAG, font=(TC_FONT_FAMILY, -1))
    except (tk.TclError, ValueError, AttributeError):
        return False
    return True


def insert_display_text(textbox: _TextInserter, index: str, text: str, tags: str | tuple[str, ...]) -> None:
    """Insert transformed text while tagging only its synthetic break spaces."""
    base_tags = (tags,) if isinstance(tags, str) else tags
    parts = add_display_break_hints(text).split(DISPLAY_BREAK_HINT)
    for part_index, part in enumerate(parts):
        if part:
            textbox.insert(index, part, base_tags)
        if part_index + 1 < len(parts):
            textbox.insert(index, DISPLAY_BREAK_HINT, (*base_tags, DISPLAY_BREAK_TAG))


def configure_hanging_indent(textbox: object, tag: str, prefix: str) -> bool:
    """Measure the actual scaled marker prefix for list continuation lines."""
    tk_text = getattr(textbox, "_textbox", None)
    if tk_text is None or not hasattr(tk_text, "tag_configure"):
        return False
    try:
        font = tkfont.Font(root=tk_text, font=apply_widget_font_scaling(textbox, (TC_FONT_FAMILY, POPUP_FONT_SIZES["content"])))
        tk_text.tag_configure(tag, lmargin1=0, lmargin2=font.measure(prefix))
    except (tk.TclError, ValueError, AttributeError):
        return False
    return True


class _PresentationTextbox(ctk.CTkTextbox):
    """CTk textbox that reapplies native Tk tag fonts after DPI changes."""

    def _set_scaling(self, *args, **kwargs):
        super()._set_scaling(*args, **kwargs)
        if hasattr(self, "_textbox"):
            configure_presentation_typography(self)
            configure_display_break_typography(self)
            callback = getattr(self, "_on_scaling_changed", None)
            if callable(callback):
                callback()


def rgb_to_hex(color: RGB) -> str:
    if len(color) != 3:
        raise ValueError("RGB color must contain exactly three values")
    for value in color:
        if not isinstance(value, int) or value < 0 or value > 255:
            raise ValueError("RGB color values must be integers from 0 to 255")
    return "#{:02X}{:02X}{:02X}".format(*color)


@dataclass(frozen=True)
class SurfaceStateColors:
    idle: RGB = DEFAULT_STATE_COLORS["idle"]
    success: RGB = DEFAULT_STATE_COLORS["success"]
    error: RGB = DEFAULT_STATE_COLORS["error"]
    warning: RGB = DEFAULT_STATE_COLORS["warning"]

    @classmethod
    def from_mapping(cls, values: Mapping[str, RGB] | None) -> SurfaceStateColors:
        if not values:
            return cls()
        allowed = {key: values[key] for key in DEFAULT_STATE_COLORS if key in values}
        return cls(**allowed)

    def hex(self, state: DialogState) -> str:
        return rgb_to_hex(getattr(self, state))


class SurfaceFlashController:
    def __init__(
        self,
        *,
        colors: SurfaceStateColors,
        apply_color: Callable[[str], None],
        schedule: Callable[[int, Callable[[], None]], str],
        cancel: Callable[[str], None],
    ) -> None:
        self._colors = colors
        self._apply_color = apply_color
        self._schedule = schedule
        self._cancel = cancel
        self._reset_job: str | None = None
        self.state: DialogState = "idle"

    def reset(self) -> None:
        self._reset_job = None
        self.state = "idle"
        self._apply_color(self._colors.hex("idle"))

    def set_state(self, state: DialogState) -> None:
        self._cancel_pending_reset()
        self.state = state
        self._apply_color(self._colors.hex(state))

    def redraw(self) -> None:
        """Repaint the current state without changing its pending lifecycle."""
        self._apply_color(self._colors.hex(self.state))

    def flash(self, state: DialogState) -> None:
        if state == "idle":
            self.set_state("idle")
            return

        self._cancel_pending_reset()
        self.state = state
        self._apply_color(self._colors.hex(state))
        duration_ms = 1000 if state == "success" else 3000
        self._reset_job = self._schedule(duration_ms, self.reset)

    def _cancel_pending_reset(self) -> None:
        if self._reset_job is not None:
            self._cancel(self._reset_job)
            self._reset_job = None


class RoundedSurfacePainter:
    def __init__(
        self,
        canvas,
        *,
        width: int,
        height: int,
        background_color: str,
        surface_color: str,
        radius: int = 18,
        inset: int = 4,
    ) -> None:
        self._canvas = canvas
        self._width = width
        self._height = height
        self._background_color = background_color
        self._surface_color = surface_color
        self._radius = radius
        self._inset = inset

    def draw(self, border_color: str) -> None:
        self._canvas.delete("surface")
        self._canvas.create_rectangle(
            0,
            0,
            self._width,
            self._height,
            fill=self._background_color,
            outline=self._background_color,
            tags="surface",
        )
        self._draw_round_rect(0, 0, self._width, self._height, self._radius, border_color)
        self._draw_round_rect(
            self._inset,
            self._inset,
            self._width - self._inset,
            self._height - self._inset,
            max(1, self._radius - self._inset),
            self._surface_color,
        )
        self._canvas.tag_lower("surface")

    def resize(self, width: int, height: int, *, radius: int | None = None, inset: int | None = None) -> None:
        self._width = width
        self._height = height
        if radius is not None:
            self._radius = radius
        if inset is not None:
            self._inset = inset

    def _draw_round_rect(self, x1: int, y1: int, x2: int, y2: int, radius: int, color: str) -> None:
        options = {"fill": color, "outline": color, "tags": "surface"}
        self._canvas.create_rectangle(x1 + radius, y1, x2 - radius, y2, **options)
        self._canvas.create_rectangle(x1, y1 + radius, x2, y2 - radius, **options)
        self._canvas.create_oval(x1, y1, x1 + radius * 2, y1 + radius * 2, **options)
        self._canvas.create_oval(x2 - radius * 2, y1, x2, y1 + radius * 2, **options)
        self._canvas.create_oval(x1, y2 - radius * 2, x1 + radius * 2, y2, **options)
        self._canvas.create_oval(x2 - radius * 2, y2 - radius * 2, x2, y2, **options)


def hide_window_from_task_switcher(window, user32=None) -> bool:
    """Hide a Windows popup from both the taskbar and Alt+Tab."""
    if user32 is None:
        if sys.platform != "win32":
            return False
        import ctypes

        user32 = ctypes.windll.user32
    try:
        window.update_idletasks()
        child = int(window.winfo_id())
        hwnd = int(user32.GetParent(child)) or child
        gwl_exstyle = -20
        ws_ex_toolwindow = 0x00000080
        ws_ex_appwindow = 0x00040000
        style = int(user32.GetWindowLongW(hwnd, gwl_exstyle))
        user32.SetWindowLongW(hwnd, gwl_exstyle, (style | ws_ex_toolwindow) & ~ws_ex_appwindow)
        user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0027)
        return True
    except (AttributeError, OSError, TypeError, ValueError):
        return False


def show_window_without_activation(window, user32=None) -> bool:
    """Show a withdrawn Windows popup without taking focus from its paste target."""
    if user32 is None:
        if sys.platform != "win32":
            try:
                window.deiconify()
                return True
            except (AttributeError, tk.TclError):
                return False
        import ctypes

        user32 = ctypes.windll.user32
    try:
        previous_foreground = int(user32.GetForegroundWindow())
        window.deiconify()
        window.update_idletasks()
        child = int(window.winfo_id())
        hwnd = int(user32.GetParent(child)) or child
        sw_show_no_activate = 4
        user32.ShowWindow(hwnd, sw_show_no_activate)
        if previous_foreground and previous_foreground != hwnd:
            user32.SetForegroundWindow(previous_foreground)
        return True
    except (AttributeError, OSError, TypeError, ValueError, tk.TclError):
        return False


class BaseDialog:
    def __init__(
        self,
        *,
        title: str,
        width: int,
        height: int,
        position: str = "center",
        state_colors: Mapping[str, RGB] | None = None,
        border_color: str | None = None,
        background_color: str = "#E9EDF3",
        surface_color: str = "#FFFFFF",
        frameless: bool = False,
        transparent_background: bool = False,
        surface_inset: int = 8,
        corner_radius: int = 18,
        track_dialog_state: bool = True,
        master: tk.Misc | None = None,
        topmost: bool = True,
        x: int | None = None,
        y: int | None = None,
        minimum_width: int | None = None,
        minimum_height: int | None = None,
        hide_from_task_switcher: bool = False,
        on_close_request: Callable[[], None] | None = None,
    ) -> None:
        del track_dialog_state
        self.pending_tasks: list[str] = []
        self._valid = True
        self.width = width
        self.height = height
        self.pinned = False
        self._drag_offset_x = 0
        self._drag_offset_y = 0
        self._on_close_request = on_close_request
        self._state_colors = SurfaceStateColors.from_mapping(state_colors)
        self._surface_inset = surface_inset
        self._corner_radius = corner_radius
        self._border_inset = max(1, surface_inset // 3)

        try:
            self.root = ctk.CTkToplevel(master) if master is not None else ctk.CTk()
            self.root.title(title)
            self.root.geometry(f"{width}x{height}")
            self.root.minsize(minimum_width or min(width, 320), minimum_height or min(height, 180))
            self.root.configure(fg_color=background_color)
            if frameless:
                self.root.overrideredirect(True)
            if transparent_background:
                try:
                    self.root.attributes("-transparentcolor", background_color)
                except Exception:
                    pass
            if topmost:
                self.root.attributes("-topmost", True)
            if x is not None and y is not None:
                self.root.geometry(f"{width}x{height}+{x}+{y}")
            else:
                self._position_window(width, height, position)

            self.canvas = tk.Canvas(
                self.root,
                bg=background_color,
                highlightthickness=0,
                bd=0,
            )
            self.canvas.pack(fill="both", expand=True)
            self._painter = RoundedSurfacePainter(
                self.canvas,
                width=width,
                height=height,
                background_color=background_color,
                surface_color=surface_color,
                radius=corner_radius,
                inset=self._border_inset,
            )
            idle_color = border_color or self._state_colors.hex("idle")
            self._painter.draw(idle_color)

            self.surface = tk.Frame(self.canvas, bg=surface_color, bd=0, highlightthickness=0)
            self._surface_window = self.canvas.create_window(
                surface_inset,
                surface_inset,
                anchor="nw",
                window=self.surface,
                width=max(1, width - surface_inset * 2),
                height=max(1, height - surface_inset * 2),
            )
            self.canvas.bind("<Configure>", self._on_canvas_configure, add="+")
            self.main_frame = self.surface

            self.lifecycle = DialogLifecycle(self.root, owns_mainloop=master is None)
            self._flash_controller = SurfaceFlashController(
                colors=self._state_colors,
                apply_color=self._painter.draw,
                schedule=self.lifecycle.schedule,
                cancel=self.lifecycle.cancel,
            )
            self.root.protocol("WM_DELETE_WINDOW", self.request_close)
            self.root.bind("<Escape>", lambda _event: self.request_close())
            self.enable_drag(self.canvas, self.surface)
            if hide_from_task_switcher:
                self.root.after_idle(lambda: hide_window_from_task_switcher(self.root))
        except Exception:
            self._valid = False
            raise
    def is_valid(self) -> bool:
        return self._valid

    def is_alive(self) -> bool:
        if not self._valid or self.lifecycle.is_closed:
            return False
        try:
            return bool(self.root.winfo_exists())
        except tk.TclError:
            return False

    def flash(self, state: DialogState) -> None:
        self._flash_controller.flash(state)

    def set_pinned(self, pinned: bool) -> None:
        self.pinned = pinned

    def toggle_pin(self) -> bool:
        self.pinned = not self.pinned
        return self.pinned

    def close(self) -> None:
        self.lifecycle.close()

    def hide_for_external_output(self) -> None:
        try:
            self.root.withdraw()
        except tk.TclError:
            pass

    def restore_after_external_output(self, *, activate: bool) -> None:
        if activate:
            try:
                self.root.deiconify()
            except tk.TclError:
                return
            self.lifecycle.focus()
            return
        show_window_without_activation(self.root)

    def request_close(self) -> str:
        """Emit the semantic close request; only the presenter destroys views."""
        if self._on_close_request is not None:
            self._on_close_request()
        else:
            self.close()
        return "break"

    def enable_drag(self, *widgets) -> None:
        for widget in widgets:
            widget.bind("<ButtonPress-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._drag_window)

    def _start_drag(self, event) -> None:
        self._drag_offset_x = event.x_root - self.root.winfo_x()
        self._drag_offset_y = event.y_root - self.root.winfo_y()

    def _drag_window(self, event) -> None:
        x, y = self.calculate_drag_position(event.x_root, event.y_root)
        self.root.geometry(f"+{x}+{y}")

    def calculate_drag_position(self, x_root: int, y_root: int) -> tuple[int, int]:
        return x_root - self._drag_offset_x, y_root - self._drag_offset_y

    def resize(self, width: int, height: int, *, x: int | None = None, y: int | None = None) -> None:
        if width == self.width and height == self.height and x is None and y is None:
            return
        self.width, self.height = width, height
        target_x = self.root.winfo_x() if x is None else x
        target_y = self.root.winfo_y() if y is None else y
        self.root.geometry(f"{width}x{height}+{target_x}+{target_y}")

    def _on_canvas_configure(self, event) -> None:
        actual_width = max(1, int(event.width))
        actual_height = max(1, int(event.height))
        width_scale = actual_width / self.width if self.width else 1.0
        height_scale = actual_height / self.height if self.height else 1.0
        observed_scale = max(0.1, min(width_scale, height_scale))
        surface_inset = max(1, round(self._surface_inset * observed_scale))
        corner_radius = max(1, round(self._corner_radius * observed_scale))
        border_inset = max(1, round(self._border_inset * observed_scale))
        self._painter.resize(
            actual_width,
            actual_height,
            radius=corner_radius,
            inset=border_inset,
        )
        self.canvas.coords(self._surface_window, surface_inset, surface_inset)
        self.canvas.itemconfigure(
            self._surface_window,
            width=max(1, actual_width - surface_inset * 2),
            height=max(1, actual_height - surface_inset * 2),
        )
        self._flash_controller.redraw()

    def _position_window(self, width: int, height: int, position: str) -> None:
        self.root.update_idletasks()
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()

        if position == "cursor":
            try:
                pointer_x = self.root.winfo_pointerx()
                pointer_y = self.root.winfo_pointery()
                x = max(20, min(pointer_x - width // 3, screen_w - width - 20))
                y = max(20, min(pointer_y - height // 4, screen_h - height - 40))
            except tk.TclError:
                x = max(20, (screen_w - width) // 2)
                y = max(20, (screen_h - height) // 2)
        else:
            x = max(20, (screen_w - width) // 2)
            y = max(20, (screen_h - height) // 2)

        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def run_dialog(self) -> None:
        self.lifecycle.run_dialog()


class _Tooltip:
    def __init__(self, widget, text: str, lifecycle: DialogLifecycle, delay_ms: int = 350) -> None:
        self.widget = widget
        self.text = text
        self.lifecycle = lifecycle
        self.delay_ms = delay_ms
        self._window: tk.Toplevel | None = None
        self._job: str | None = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event=None) -> None:
        self._cancel()
        self._job = self.lifecycle.schedule(self.delay_ms, self._show)

    def _show(self) -> None:
        self._job = None
        if self._window is not None:
            return
        x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
        self._window = tk.Toplevel(self.widget)
        self._window.wm_overrideredirect(True)
        configure_tooltip_layer(self._window, self.widget.winfo_toplevel())
        self._window.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            self._window,
            text=self.text,
            bg="#0F172A",
            fg="#FFFFFF",
            padx=8,
            pady=4,
            font=apply_widget_font_scaling(self.widget, (TC_FONT_FAMILY, POPUP_FONT_SIZES["tooltip"])),
            justify="left",
        )
        label.pack()

    def set_text(self, text: str) -> None:
        self.text = text
        if self._window is None:
            return
        for child in self._window.winfo_children():
            if isinstance(child, tk.Label):
                child.configure(text=text)

    def _hide(self, _event=None) -> None:
        self._cancel()
        if self._window is not None:
            self._window.destroy()
            self._window = None

    def _cancel(self) -> None:
        if self._job is not None:
            self.lifecycle.cancel(self._job)
            self._job = None


def configure_tooltip_layer(window: object, owner: object) -> None:
    """Keep tooltips above the always-on-top popup without taking focus."""
    try:
        window.wm_transient(owner)  # type: ignore[attr-defined]
        window.attributes("-topmost", True)  # type: ignore[attr-defined]
        window.lift(owner)  # type: ignore[attr-defined]
    except (tk.TclError, AttributeError):
        pass


@dataclass(frozen=True)
class ResultActionSpec:
    slot_id: ResultActionId
    icon: str
    tooltip: str
    active_icon: str | None = None
    active_tooltip: str | None = None
    active_color: str = ACTION_COLOR
    active_hover_color: str = ACTION_HOVER_COLOR


STANDARD_RESULT_ACTIONS: tuple[ResultActionSpec, ...] = (
    ResultActionSpec(
        slot_id="speaker",
        icon=SPEAKER_ICON,
        tooltip="Speak result (Ctrl+Q)",
        active_icon=STOP_ICON,
        active_tooltip="Stop speaking (Ctrl+Q)",
        active_color=SPEAKER_ACTIVE_COLOR,
        active_hover_color=SPEAKER_ACTIVE_HOVER_COLOR,
    ),
    ResultActionSpec(
        slot_id="copy",
        icon=COPY_ICON,
        tooltip="Copy result (Ctrl+C)",
        active_icon=CHECK_ICON,
        active_tooltip="Copy accepted (Ctrl+C)",
        active_color="#00B04F",
        active_hover_color="#00B04F",
    ),
    ResultActionSpec(slot_id="paste", icon=PASTE_ICON, tooltip="Paste result (Ctrl+V)"),
    ResultActionSpec(
        slot_id="archive",
        icon=ARCHIVE_ICON,
        tooltip="Archive result (Ctrl+S)",
        active_icon=CHECK_ICON,
        active_tooltip="Archive accepted (Ctrl+S)",
        active_color="#00B04F",
        active_hover_color="#00B04F",
    ),
    ResultActionSpec(
        slot_id="follow_up",
        icon=FOLLOW_UP_ICON,
        tooltip="Ask follow-up (Ctrl+/)",
        active_tooltip="Close follow-up (Ctrl+/)",
        active_color=FOLLOW_ACTIVE_COLOR,
        active_hover_color=ACTION_HOVER_COLOR,
    ),
)


class StandardResultActions:
    def __init__(self, surface: BaseResultSurface) -> None:
        self._surface = surface
        self._specs = {spec.slot_id: spec for spec in STANDARD_RESULT_ACTIONS}
        self._pulse_jobs: dict[ResultActionId, str] = {}
        self._buttons = {
            spec.slot_id: surface.add_action_slot(
                spec.slot_id,
                spec.icon,
                None,
                width=24,
                tooltip=spec.tooltip,
                overflow=spec.slot_id in {"paste", "archive"},
            )
            for spec in STANDARD_RESULT_ACTIONS
        }

    def configure(
        self,
        *,
        on_speak: Callable[[], None] | None = None,
        on_copy: Callable[[], None] | None = None,
        on_paste: Callable[[], None] | None = None,
        on_archive: Callable[[], None] | None = None,
        on_follow_up: Callable[[], None] | None = None,
    ) -> None:
        self._set_command("speaker", on_speak)
        self._set_command("copy", on_copy)
        self._set_command("paste", on_paste)
        self._set_command("archive", on_archive)
        self._set_command("follow_up", on_follow_up)

    def set_speaker_active(self, active: bool) -> None:
        self._set_active("speaker", active)

    def set_follow_up_active(self, active: bool) -> None:
        self._set_active("follow_up", active)

    def pulse(self, slot_id: ResultActionId, duration_ms: int = 1000) -> None:
        previous_job = self._pulse_jobs.pop(slot_id, None)
        if previous_job is not None:
            self._surface.dialog.lifecycle.cancel(previous_job)
        self._set_active(slot_id, True)

        def reset() -> None:
            self._pulse_jobs.pop(slot_id, None)
            self._set_active(slot_id, False)

        self._pulse_jobs[slot_id] = self._surface.dialog.lifecycle.schedule(duration_ms, reset)

    def pulse_error(self, slot_id: ResultActionId, duration_ms: int = 1000) -> None:
        button = self._buttons[slot_id]
        button.configure(text="!", fg_color="#E81123", hover_color="#E81123", text_color=CONTENT_COLOR)
        self._surface.dialog.lifecycle.schedule(duration_ms, lambda: self._set_active(slot_id, False))

    def set_enabled(self, slot_id: ResultActionId, enabled: bool) -> None:
        self._buttons[slot_id].configure(state="normal" if enabled else "disabled")

    def _set_command(self, slot_id: ResultActionId, command: Callable[[], None] | None) -> None:
        self._buttons[slot_id].configure(command=command)
        self.set_enabled(slot_id, command is not None)

    def _set_active(self, slot_id: ResultActionId, active: bool) -> None:
        spec = self._specs[slot_id]
        self._buttons[slot_id].configure(**self.style_for(spec, active))
        tooltip = spec.active_tooltip if active and spec.active_tooltip else spec.tooltip
        self._surface.set_action_tooltip(slot_id, tooltip)

    @staticmethod
    def style_for(spec: ResultActionSpec, active: bool) -> dict[str, str]:
        if not active:
            return {
                "text": spec.icon,
                "fg_color": ACTION_COLOR,
                "hover_color": ACTION_HOVER_COLOR,
                "text_color": CONTENT_COLOR,
            }
        return {
            "text": spec.active_icon or spec.icon,
            "fg_color": spec.active_color,
            "hover_color": spec.active_hover_color,
            "text_color": CONTENT_COLOR,
        }


class BaseResultSurface:
    def __init__(self, dialog: BaseDialog) -> None:
        self.dialog = dialog
        self.root = dialog.surface
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(4, weight=1)
        self._action_buttons: dict[str, ctk.CTkButton] = {}
        self._action_tooltips: dict[str, _Tooltip] = {}
        self.follow_up_visible = False
        self.overflow_expanded = False
        self._feedback_submit: Callable[[FeedbackOutcome, str, str, bool], None] | None = None
        self._feedback_state: FeedbackOperationState = "idle"
        self._feedback_overlay_open = False
        self._feedback_contract: ActionFeedbackContract | None = None
        self._feedback_success_job: str | None = None
        self._feedback_pending_payload: tuple[FeedbackOutcome, str, str, bool] | None = None
        self._guidance_job: str | None = None
        self._rendered_pinned_state: bool | None = None
        self._build()

    def _build(self) -> None:
        self.header = ctk.CTkFrame(self.root, fg_color=SURFACE_BG)
        self.header.grid(row=0, column=0, sticky="ew", padx=9, pady=(3, 0))
        self.header.grid_columnconfigure(0, weight=1)

        self.title_area = ctk.CTkFrame(self.header, fg_color=SURFACE_BG)
        self.title_area.grid(row=0, column=0, sticky="w")
        self.title_label = ctk.CTkLabel(
            self.title_area,
            text="",
            font=ctk.CTkFont(family=TC_FONT_FAMILY, size=POPUP_FONT_SIZES["interface"], weight="bold"),
            text_color=TITLE_COLOR,
            wraplength=330,
        )
        self.title_label.pack(anchor="w")

        self.window_actions = ctk.CTkFrame(self.header, fg_color=SURFACE_BG)
        self.window_actions.grid(row=0, column=1, sticky="ne")
        self.info_button = ctk.CTkButton(
            self.window_actions,
            text="ⓘ",
            width=18,
            height=18,
            corner_radius=9,
            fg_color=SURFACE_BG,
            hover_color="#3A3A3A",
            text_color="#8A8A8A",
            font=ctk.CTkFont(family=TC_FONT_FAMILY, size=POPUP_FONT_SIZES["interface"]),
            command=self.toggle_feedback_overlay,
        )
        self._info_tooltip = _Tooltip(self.info_button, "", self.dialog.lifecycle)
        self.guidance_coachmark = ctk.CTkFrame(
            self.root,
            fg_color="#0F172A",
            border_width=1,
            border_color="#36516F",
            corner_radius=8,
        )
        self.guidance_coachmark_label = ctk.CTkLabel(
            self.guidance_coachmark,
            text="",
            anchor="w",
            justify="left",
            wraplength=285,
            text_color="#FFFFFF",
            font=ctk.CTkFont(family=TC_FONT_FAMILY, size=POPUP_FONT_SIZES["auxiliary"]),
        )
        self.guidance_coachmark_label.pack(fill="x", padx=9, pady=7)
        self.close_button = ctk.CTkButton(
            self.window_actions,
            text="×",
            width=18,
            height=18,
            corner_radius=9,
            fg_color=SURFACE_BG,
            hover_color="#3A3A3A",
            text_color="#8A8A8A",
            font=ctk.CTkFont(family=ACTION_ICON_FONT_FAMILY, size=10, weight="bold"),
            command=self.dialog.close,
        )
        self.close_button.pack(side="left", padx=(0, 4))
        self.pin_button = ctk.CTkButton(
            self.window_actions,
            text=PIN_ICON,
            width=18,
            height=18,
            corner_radius=9,
            fg_color=SURFACE_BG,
            hover_color="#3A3A3A",
            text_color="#8A8A8A",
            font=ctk.CTkFont(family=ACTION_ICON_FONT_FAMILY, size=10),
            command=self.toggle_pin,
        )
        self.pin_button.pack(side="left")
        self._pin_tooltip = _Tooltip(self.pin_button, "Keep open (Ctrl+E or double-click header)", self.dialog.lifecycle)
        self.dialog.enable_drag(self.header, self.title_area, self.title_label)

        self.actions = ctk.CTkFrame(self.root, fg_color=SURFACE_BG)
        self.actions.grid(row=1, column=0, sticky="ew", padx=9, pady=(0, 0))
        self.overflow_actions = ctk.CTkFrame(self.root, fg_color=SURFACE_BG)
        self._back_button = self.add_action_slot("back", "←", None, width=24, tooltip="Previous result")
        self._back_button.pack_forget()
        self.standard_actions = StandardResultActions(self)
        self._overflow_button = self.add_action_slot("overflow", "▶", self.toggle_overflow, width=24, tooltip="More actions")
        self._overflow_button.pack_configure(side="right", padx=(12, 0))
        self.action_status_label = ctk.CTkLabel(self.actions, text="", text_color="#8A8A8A", font=ctk.CTkFont(family=TC_FONT_FAMILY, size=POPUP_FONT_SIZES["auxiliary"]))
        self.action_status_label.pack(side="right", padx=(8, 0))

        self.source_label = ctk.CTkLabel(
            self.root,
            text="",
            anchor="w",
            justify="left",
            font=ctk.CTkFont(family=TC_FONT_FAMILY, size=POPUP_FONT_SIZES["interface"]),
            text_color=ANALYZING_COLOR,
            wraplength=0,
        )
        self.source_label.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 0))

        self.content_text = _PresentationTextbox(
            self.root,
            fg_color=SURFACE_BG,
            border_width=0,
            border_spacing=0,
            corner_radius=0,
            wrap="word",
            font=ctk.CTkFont(family=TC_FONT_FAMILY, size=POPUP_FONT_SIZES["content"]),
            text_color=CONTENT_COLOR,
            scrollbar_button_color="#4A4A4A",
            scrollbar_button_hover_color="#5A5A5A",
            height=170,
            pady=0,
        )
        self.content_text.grid(row=4, column=0, sticky="nsew", padx=12, pady=(0, 2))
        self.content_text.tag_config("heading", foreground=CONTENT_COLOR)
        self.content_text.tag_config("body", foreground=CONTENT_COLOR)
        self.content_text.tag_config("loading", foreground=ANALYZING_COLOR)
        for tag, style in PRESENTATION_TAG_STYLES.items():
            self.content_text.tag_config(tag, **style)
        configure_presentation_typography(self.content_text)
        configure_display_break_typography(self.content_text)
        self._list_indent_prefixes: dict[str, str] = {}
        self.content_text._on_scaling_changed = self._reapply_list_indents

        self.model_label = ctk.CTkLabel(
            self.root,
            text="",
            anchor="e",
            height=11,
            font=ctk.CTkFont(family=TC_FONT_FAMILY, size=POPUP_FONT_SIZES["model"]),
            text_color=MODEL_COLOR,
        )
        self.model_label.grid(row=5, column=0, sticky="e", padx=12, pady=(0, 2))

        self.feedback_frame = ctk.CTkFrame(
            self.root,
            fg_color="#252525",
            border_width=1,
            border_color="#454545",
            corner_radius=9,
        )
        feedback_header = ctk.CTkFrame(self.feedback_frame, fg_color="transparent")
        feedback_header.pack(fill="x", padx=10, pady=(9, 4))
        self.feedback_prompt = ctk.CTkLabel(
            feedback_header,
            text="這次結果符合預期嗎？",
            font=ctk.CTkFont(family=TC_FONT_FAMILY, size=POPUP_FONT_SIZES["interface"], weight="bold"),
            text_color=CONTENT_COLOR,
        )
        self.feedback_prompt.pack(side="left")
        self.feedback_close_button = ctk.CTkButton(
            feedback_header,
            text="×",
            width=20,
            height=20,
            corner_radius=10,
            fg_color="transparent",
            hover_color="#3A3A3A",
            text_color="#A9BACB",
            command=self.close_feedback_overlay,
        )
        self.feedback_close_button.pack(side="right")
        feedback_choices = ctk.CTkFrame(self.feedback_frame, fg_color="transparent")
        feedback_choices.pack(fill="x", padx=10, pady=(2, 5))
        self.feedback_buttons: list[ctk.CTkButton] = []
        for label, outcome, width in (("符合預期", "helpful", 72), ("需要調整", "needs_adjustment", 72)):
            button = ctk.CTkButton(
                feedback_choices,
                text=label,
                height=22,
                width=width,
                corner_radius=6,
                fg_color="#3A3A3A",
                hover_color="#4A4A4A",
                font=ctk.CTkFont(family=TC_FONT_FAMILY, size=POPUP_FONT_SIZES["auxiliary"]),
                command=(lambda selected=outcome: self._choose_feedback(selected)),
            )
            button.pack(side="left", padx=(0, 5))
            self.feedback_buttons.append(button)
        self.feedback_save_case = tk.BooleanVar(value=False)
        self.feedback_case_checkbox = ctk.CTkCheckBox(
            self.feedback_frame,
            text="儲存供日後改善（包含原文與結果，僅存在本機）",
            variable=self.feedback_save_case,
            text_color=CONTENT_COLOR,
            border_color="#8A8A8A",
            font=ctk.CTkFont(family=TC_FONT_FAMILY, size=POPUP_FONT_SIZES["auxiliary"]),
        )
        self.feedback_case_checkbox.pack(anchor="w", padx=10, pady=(2, 5))
        self.feedback_status = ctk.CTkLabel(
            self.feedback_frame,
            text="",
            font=ctk.CTkFont(family=TC_FONT_FAMILY, size=POPUP_FONT_SIZES["auxiliary"]),
            text_color=ANALYZING_COLOR,
        )
        self.feedback_status.pack(anchor="w", padx=10, pady=(0, 7))
        self.feedback_retry_button = ctk.CTkButton(
            self.feedback_frame,
            text="重試",
            width=48,
            height=24,
            command=self._retry_feedback,
            font=ctk.CTkFont(family=TC_FONT_FAMILY, size=POPUP_FONT_SIZES["auxiliary"]),
        )

        self.feedback_detail = ctk.CTkFrame(self.feedback_frame, fg_color="transparent")
        self.feedback_reason_buttons = ctk.CTkFrame(self.feedback_detail, fg_color="transparent")
        self.feedback_reason_buttons.pack(fill="x")
        self.feedback_other = ctk.CTkFrame(self.feedback_detail, fg_color="transparent")
        self.feedback_note = ctk.CTkEntry(
            self.feedback_other,
            placeholder_text="請補充一句具體情況",
            height=28,
            font=ctk.CTkFont(family=TC_FONT_FAMILY, size=POPUP_FONT_SIZES["auxiliary"]),
        )
        self.feedback_note.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.feedback_submit_button = ctk.CTkButton(
            self.feedback_other,
            text="送出",
            width=48,
            height=28,
            command=self._submit_other,
            font=ctk.CTkFont(family=TC_FONT_FAMILY, size=POPUP_FONT_SIZES["auxiliary"]),
        )
        self.feedback_submit_button.pack(side="left")

        # Feedback is a transient layer. It must never consume a grid row or
        # reduce the canonical result area's height.
        self.dialog.root.bind("<Escape>", self._handle_escape)

        self.follow_row = ctk.CTkFrame(self.root, fg_color=SURFACE_BG)
        self.follow_row.grid_columnconfigure(0, weight=1)
        self.follow_entry = ctk.CTkEntry(
            self.follow_row,
            height=30,
            corner_radius=9,
            border_width=1,
            border_color="#4A4A4A",
            fg_color=SURFACE_BG,
            text_color=CONTENT_COLOR,
            font=ctk.CTkFont(family=TC_FONT_FAMILY, size=POPUP_FONT_SIZES["interface"]),
        )
        self.follow_entry.grid(row=0, column=0, sticky="ew", padx=(0, 7))
        self.follow_send_button = ctk.CTkButton(
            self.follow_row,
            text="Send",
            width=49,
            height=30,
            corner_radius=9,
            fg_color=ACTION_COLOR,
            hover_color=ACTION_HOVER_COLOR,
            font=ctk.CTkFont(family=TC_FONT_FAMILY, size=POPUP_FONT_SIZES["interface"]),
        )
        self.follow_send_button.grid(row=0, column=1, sticky="e")

    def set_title(self, title: str) -> None:
        self.title_label.configure(text=title)

    def set_source_preview(self, text: str) -> None:
        self.source_label.configure(text=ellipsize_source_preview(text))

    def set_model(self, model: str) -> None:
        self.model_label.configure(text=f"model: {model}")

    def configure_action_contract(self, contract: ActionFeedbackContract | None, input_source: str) -> None:
        if contract is None:
            self.info_button.pack_forget()
            self._feedback_contract = None
            self.close_feedback_overlay()
            return
        self._feedback_contract = contract
        self._info_tooltip.set_text(action_contract_tooltip_text(contract))
        if not self.info_button.winfo_manager():
            self.info_button.pack(side="left", padx=(0, 4), before=self.close_button)

    def show_action_guidance_hint(self) -> None:
        if self._feedback_contract is not None and self.info_button.winfo_manager():
            if self._guidance_job is not None:
                self.dialog.lifecycle.cancel(self._guidance_job)
            self.guidance_coachmark_label.configure(text=action_contract_tooltip_text(self._feedback_contract))
            self.guidance_coachmark.place(relx=0.97, y=30, anchor="ne", relwidth=0.82)
            self.guidance_coachmark.lift()
            self._guidance_job = self.dialog.lifecycle.schedule(3500, self.hide_action_guidance_hint)

    def hide_action_guidance_hint(self) -> None:
        self.guidance_coachmark.place_forget()
        if self._guidance_job is not None:
            self.dialog.lifecycle.cancel(self._guidance_job)
            self._guidance_job = None

    def configure_feedback(
        self,
        contract: ActionFeedbackContract | None,
        state: FeedbackOperationState,
        message: str,
        on_submit: Callable[[FeedbackOutcome, str, str, bool], None] | None,
    ) -> None:
        if contract is None or on_submit is None:
            self.hide_feedback()
            return
        self._feedback_submit = on_submit
        self._feedback_contract = contract
        self._feedback_state = state
        for child in self.feedback_reason_buttons.winfo_children():
            child.destroy()
        for reason in contract.reasons:
            button = ctk.CTkButton(
                self.feedback_reason_buttons,
                text=reason.label,
                anchor="w",
                height=25,
                fg_color="#3A3A3A",
                hover_color="#4A4A4A",
                font=ctk.CTkFont(family=TC_FONT_FAMILY, size=POPUP_FONT_SIZES["auxiliary"]),
                command=lambda reason_id=reason.id: self._choose_reason(reason_id),
            )
            button.pack(fill="x", pady=(0, 4))
        enabled = state not in {"pending", "succeeded"}
        for button in self.feedback_buttons:
            button.configure(state="normal" if enabled else "disabled")
        for button in self.feedback_reason_buttons.winfo_children():
            button.configure(state="normal" if enabled else "disabled")
        self.feedback_submit_button.configure(state="normal" if enabled else "disabled")
        self.feedback_case_checkbox.configure(state="normal" if enabled else "disabled")
        self.feedback_status.configure(
            text=message or ("正在儲存…" if state == "pending" else ""),
            text_color="#00B04F" if state == "succeeded" else "#E81123" if state == "failed" else ANALYZING_COLOR,
        )
        self.feedback_retry_button.pack_forget()
        if state == "failed" and self._feedback_pending_payload is not None:
            self.feedback_retry_button.pack(anchor="w", padx=10, pady=(0, 8))
        if state == "succeeded":
            self.feedback_detail.pack_forget()
            if self._feedback_overlay_open:
                if self._feedback_success_job is not None:
                    self.dialog.lifecycle.cancel(self._feedback_success_job)
                self._feedback_success_job = self.dialog.lifecycle.schedule(700, self.close_feedback_overlay)

    def hide_feedback(self) -> None:
        self.close_feedback_overlay()
        self._feedback_submit = None
        self._feedback_state = "idle"

    def toggle_feedback_overlay(self) -> bool:
        if self._feedback_submit is None:
            return False
        if self._feedback_state == "succeeded":
            self.show_action_message("已記錄回饋")
            return True
        self.hide_action_guidance_hint()
        if self._feedback_overlay_open:
            self.close_feedback_overlay()
            return True
        self.feedback_save_case.set(False)
        self.feedback_note.delete(0, "end")
        self.feedback_detail.pack_forget()
        self.feedback_other.pack_forget()
        self.feedback_retry_button.pack_forget()
        if self._feedback_state not in {"pending", "failed", "succeeded"}:
            self.feedback_status.configure(text="")
        self.feedback_frame.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.9)
        self.feedback_frame.lift()
        self._feedback_overlay_open = True
        return True

    def close_feedback_overlay(self) -> None:
        self.feedback_frame.place_forget()
        self._feedback_overlay_open = False
        if self._feedback_success_job is not None:
            self.dialog.lifecycle.cancel(self._feedback_success_job)
            self._feedback_success_job = None

    def _handle_escape(self, _event=None) -> str:
        if self._feedback_overlay_open:
            self.close_feedback_overlay()
        else:
            self.dialog.request_close()
        return "break"

    def _choose_feedback(self, outcome: FeedbackOutcome) -> None:
        if outcome == "needs_adjustment":
            self.feedback_detail.pack(fill="x", padx=10, pady=(0, 7), before=self.feedback_case_checkbox)
            return
        self._send_feedback(outcome, "", "")

    def _choose_reason(self, reason: str) -> None:
        if reason == "other":
            self.feedback_other.pack(fill="x", pady=(2, 0))
            self.dialog.lifecycle.focus(self.feedback_note)
            return
        self._send_feedback("needs_adjustment", reason, "")

    def _submit_other(self) -> None:
        note = self.feedback_note.get().strip()
        if not note:
            self.feedback_status.configure(text="請補充一句具體情況", text_color="#E81123")
            return
        self._send_feedback("needs_adjustment", "other", note)

    def _send_feedback(self, outcome: FeedbackOutcome, reason: str, note: str) -> None:
        if self._feedback_submit is None:
            return
        payload = (outcome, reason, note, bool(self.feedback_save_case.get()))
        self._feedback_pending_payload = payload
        self._show_local_feedback_pending()
        self._feedback_submit(*payload)

    def _retry_feedback(self) -> None:
        if self._feedback_submit is not None and self._feedback_pending_payload is not None:
            self._show_local_feedback_pending()
            self._feedback_submit(*self._feedback_pending_payload)

    def _show_local_feedback_pending(self) -> None:
        self._feedback_state = "pending"
        for button in (*self.feedback_buttons, *self.feedback_reason_buttons.winfo_children()):
            button.configure(state="disabled")
        self.feedback_submit_button.configure(state="disabled")
        self.feedback_case_checkbox.configure(state="disabled")
        self.feedback_retry_button.pack_forget()
        self.feedback_status.configure(text="正在儲存…", text_color=ANALYZING_COLOR)

    def configure_standard_actions(
        self,
        *,
        on_speak: Callable[[], None] | None = None,
        on_copy: Callable[[], None] | None = None,
        on_paste: Callable[[], None] | None = None,
        on_archive: Callable[[], None] | None = None,
        on_follow_up: Callable[[], None] | None = None,
    ) -> None:
        self.standard_actions.configure(
            on_speak=on_speak,
            on_copy=on_copy,
            on_paste=on_paste,
            on_archive=on_archive,
            on_follow_up=on_follow_up,
        )

    def configure_back_action(self, command: Callable[[], None] | None) -> None:
        self._back_button.configure(command=command, state="normal" if command is not None else "disabled")
        if command is None:
            self._back_button.pack_forget()
        elif not self._back_button.winfo_manager():
            self._back_button.pack(side="left", padx=(0, 5), before=self.standard_actions._buttons["speaker"])

    def set_speaker_active(self, active: bool) -> None:
        self.standard_actions.set_speaker_active(active)

    def set_follow_up_active(self, active: bool) -> None:
        self.standard_actions.set_follow_up_active(active)

    def set_standard_action_enabled(self, slot_id: ResultActionId, enabled: bool) -> None:
        self.standard_actions.set_enabled(slot_id, enabled)

    def pulse_standard_action(self, slot_id: ResultActionId, duration_ms: int = 1000) -> None:
        self.standard_actions.pulse(slot_id, duration_ms)

    def pulse_standard_action_error(self, slot_id: ResultActionId, duration_ms: int = 1000) -> None:
        self.standard_actions.pulse_error(slot_id, duration_ms)

    def show_action_message(self, text: str, duration_ms: int = 1000) -> None:
        self.action_status_label.configure(text=text)
        self.dialog.lifecycle.schedule(duration_ms, lambda: self.action_status_label.configure(text=""))

    def add_action_slot(
        self,
        slot_id: str,
        label: str,
        command: Callable[[], None] | None,
        *,
        width: int,
        tooltip: str | None = None,
        text_color: str = CONTENT_COLOR,
        overflow: bool = False,
    ) -> ctk.CTkButton:
        button = ctk.CTkButton(
            self.overflow_actions if overflow else self.actions,
            text=label,
            width=width,
            height=22,
            corner_radius=6,
            fg_color=ACTION_COLOR,
            hover_color=ACTION_HOVER_COLOR,
            text_color=text_color,
            font=ctk.CTkFont(family=ACTION_ICON_FONT_FAMILY, size=10),
            command=command,
        )
        button.pack(side="left", padx=(0, 5))
        if tooltip:
            self._action_tooltips[slot_id] = _Tooltip(button, tooltip, self.dialog.lifecycle)
        self._action_buttons[slot_id] = button
        return button

    def toggle_overflow(self) -> bool:
        self.overflow_expanded = not self.overflow_expanded
        if self.overflow_expanded:
            self.overflow_actions.grid(row=2, column=0, sticky="w", padx=12, pady=(2, 2))
        else:
            self.overflow_actions.grid_forget()
        self._overflow_button.configure(text="▼" if self.overflow_expanded else "▶")
        self.set_action_tooltip("overflow", "Hide extra actions" if self.overflow_expanded else "More actions")
        return self.overflow_expanded

    def collapse_overflow(self) -> None:
        if self.overflow_expanded:
            self.toggle_overflow()

    def set_action_tooltip(self, slot_id: str, text: str) -> None:
        tooltip = self._action_tooltips.get(slot_id)
        if tooltip is not None:
            tooltip.set_text(text)

    def set_loading(self, text: str = "Loading result...") -> None:
        self.set_content_chunks([(text, "loading")])

    def set_sections(self, sections: list[tuple[str, str]]) -> None:
        chunks: list[tuple[str, str]] = []
        for heading, body in sections:
            chunks.extend([(f"{heading}\n", "heading"), (f"{body}\n\n", "body")])
        self.set_content_chunks(chunks)

    def set_content_chunks(self, chunks: list[tuple[str, str]]) -> None:
        self.content_text.configure(state="normal")
        self.content_text.delete("1.0", "end")
        for text, tag in chunks:
            insert_display_text(self.content_text, "end", text, tag)
        self.content_text.configure(state="disabled")

    def set_presentation_document(self, document: PresentationDocument) -> None:
        self.content_text.configure(state="normal")
        self.content_text.delete("1.0", "end")
        self._list_indent_prefixes.clear()
        try:
            for block_index, block in enumerate(document.blocks):
                previous_last_char = ""
                block_tag = "paragraph"
                prefix = ""
                if block.kind == "heading":
                    block_tag = f"heading_{min(max(block.level, 1), 3)}"
                elif block.kind == "unordered_item":
                    block_tag, prefix = "list", "• "
                elif block.kind == "ordered_item":
                    block_tag, prefix = "list", f"{block.ordinal or 1}. "
                indent_tag: str | None = None
                if prefix:
                    indent_tag = f"list_indent_{block_index}"
                    self._list_indent_prefixes[indent_tag] = prefix
                    configure_hanging_indent(self.content_text, indent_tag, prefix)
                if prefix:
                    assert indent_tag is not None
                    insert_display_text(self.content_text, "end", prefix, (block_tag, indent_tag))
                for span in block.spans:
                    tags: tuple[str, ...] = ((block_tag,) if span.style == "plain" else (block_tag, span.style))
                    if indent_tag is not None:
                        tags += (indent_tag,)
                    if previous_last_char and span.text and display_break_opportunity(previous_last_char, span.text[0]):
                        self.content_text.insert("end", DISPLAY_BREAK_HINT, (*tags, DISPLAY_BREAK_TAG))
                    insert_display_text(self.content_text, "end", span.text, tags)
                    if span.text:
                        previous_last_char = span.text[-1]
                self.content_text.insert("end", "\n", (block_tag,) if indent_tag is None else (block_tag, indent_tag))
        except (tk.TclError, ValueError):
            self.content_text.delete("1.0", "end")
            insert_display_text(self.content_text, "end", document.fallback_text, "body")
        self.content_text.configure(state="disabled")

    def _reapply_list_indents(self) -> None:
        for tag, prefix in self._list_indent_prefixes.items():
            configure_hanging_indent(self.content_text, tag, prefix)

    def selected_text(self) -> str | None:
        try:
            selected = strip_display_break_hints(self.content_text.get("sel.first", "sel.last")).strip()
        except (tk.TclError, AttributeError):
            return None
        return selected or None

    def bind_header_double_click(self, callback: Callable) -> None:
        for widget in (self.header, self.title_area, self.title_label):
            widget.bind("<Double-Button-1>", callback, add="+")

    def set_pinned_state(self, pinned: bool) -> None:
        self.dialog.set_pinned(pinned)
        if getattr(self, "_rendered_pinned_state", None) is pinned:
            return
        self.pin_button.configure(
            text=UNPIN_ICON if pinned else PIN_ICON,
            fg_color=ACTION_HOVER_COLOR if pinned else SURFACE_BG,
            hover_color="#2F8DCE" if pinned else "#3A3A3A",
            text_color=CONTENT_COLOR if pinned else "#8A8A8A",
        )
        self._pin_tooltip.set_text(
            "Unpin (Ctrl+E or double-click header)" if pinned else "Keep open (Ctrl+E or double-click header)"
        )
        self._rendered_pinned_state = pinned

    def toggle_pin(self) -> bool:
        pinned = self.dialog.toggle_pin()
        self.set_pinned_state(pinned)
        return pinned

    def show_follow_up(self, initial_text: str = "") -> None:
        if not self.follow_up_visible:
            self.follow_row.grid(row=5, column=0, sticky="ew", padx=12, pady=(0, 12))
            self.follow_up_visible = True
        if initial_text:
            self.follow_entry.delete(0, "end")
            self.follow_entry.insert(0, initial_text)
        self.dialog.lifecycle.focus(self.follow_entry)

    def hide_follow_up(self) -> None:
        if self.follow_up_visible:
            self.follow_row.grid_forget()
            self.follow_up_visible = False
