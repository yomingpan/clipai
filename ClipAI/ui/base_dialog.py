from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from typing import Callable, Literal, Mapping

import customtkinter as ctk

from ClipAI.ui.dialog_lifecycle import DialogLifecycle

DialogState = Literal["idle", "success", "error", "warning"]
ResultActionId = Literal["speaker", "copy", "paste", "archive", "follow_up"]
RGB = tuple[int, int, int]

DEFAULT_STATE_COLORS: dict[DialogState, RGB] = {
    "idle": (0, 119, 200),
    "success": (0, 176, 79),
    "error": (232, 17, 35),
    "warning": (255, 215, 0),
}

SURFACE_BG = "#2B2B2B"
TITLE_COLOR = "#305B9C"
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
SPEAKER_ICON = "\uE767"
STOP_ICON = "\uE71A"
COPY_ICON = "\uE77F"
PASTE_ICON = "↪"
ARCHIVE_ICON = "▣"
FOLLOW_UP_ICON = "\uE8BD"
CHECK_ICON = "\uE73E"
PIN_ICON = "\uE718"
UNPIN_ICON = "\uE77A"


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

    def _draw_round_rect(self, x1: int, y1: int, x2: int, y2: int, radius: int, color: str) -> None:
        options = {"fill": color, "outline": color, "tags": "surface"}
        self._canvas.create_rectangle(x1 + radius, y1, x2 - radius, y2, **options)
        self._canvas.create_rectangle(x1, y1 + radius, x2, y2 - radius, **options)
        self._canvas.create_oval(x1, y1, x1 + radius * 2, y1 + radius * 2, **options)
        self._canvas.create_oval(x2 - radius * 2, y1, x2, y1 + radius * 2, **options)
        self._canvas.create_oval(x1, y2 - radius * 2, x1 + radius * 2, y2, **options)
        self._canvas.create_oval(x2 - radius * 2, y2 - radius * 2, x2, y2, **options)


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
    ) -> None:
        del track_dialog_state
        self.pending_tasks: list[str] = []
        self._valid = True
        self.width = width
        self.height = height
        self.pinned = False
        self._drag_offset_x = 0
        self._drag_offset_y = 0
        self._state_colors = SurfaceStateColors.from_mapping(state_colors)

        try:
            self.root = ctk.CTkToplevel(master) if master is not None else ctk.CTk()
            self.root.title(title)
            self.root.geometry(f"{width}x{height}")
            self.root.minsize(min(width, 320), min(height, 180))
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
            self._position_window(width, height, position)

            self.canvas = tk.Canvas(
                self.root,
                width=width,
                height=height,
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
                inset=surface_inset // 2,
            )
            idle_color = border_color or self._state_colors.hex("idle")
            self._painter.draw(idle_color)

            self.surface = tk.Frame(self.canvas, bg=surface_color, bd=0, highlightthickness=0)
            self.canvas.create_window(
                surface_inset,
                surface_inset,
                anchor="nw",
                window=self.surface,
                width=width - surface_inset * 2,
                height=height - surface_inset * 2,
            )
            self.main_frame = self.surface

            self.lifecycle = DialogLifecycle(self.root, owns_mainloop=master is None)
            self._flash_controller = SurfaceFlashController(
                colors=self._state_colors,
                apply_color=self._painter.draw,
                schedule=self.lifecycle.schedule,
                cancel=self.lifecycle.cancel,
            )
            self.root.protocol("WM_DELETE_WINDOW", self.lifecycle.close)
            self.root.bind("<Escape>", lambda _event: self.lifecycle.close())
            self.enable_drag(self.canvas, self.surface)
        except Exception:
            self._valid = False
            raise

    def is_valid(self) -> bool:
        return self._valid

    def flash(self, state: DialogState) -> None:
        self._flash_controller.flash(state)

    def set_pinned(self, pinned: bool) -> None:
        self.pinned = pinned

    def toggle_pin(self) -> bool:
        self.pinned = not self.pinned
        return self.pinned

    def close(self) -> None:
        self.lifecycle.close()

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
        self._window.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            self._window,
            text=self.text,
            bg="#0F172A",
            fg="#FFFFFF",
            padx=8,
            pady=4,
            font=(TC_FONT_FAMILY, 9),
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
        tooltip="Speak result",
        active_icon=STOP_ICON,
        active_tooltip="Stop speaking",
        active_color=SPEAKER_ACTIVE_COLOR,
        active_hover_color=SPEAKER_ACTIVE_HOVER_COLOR,
    ),
    ResultActionSpec(
        slot_id="copy",
        icon=COPY_ICON,
        tooltip="Copy result",
        active_icon=CHECK_ICON,
        active_tooltip="Copy accepted",
        active_color="#00B04F",
        active_hover_color="#00B04F",
    ),
    ResultActionSpec(slot_id="paste", icon=PASTE_ICON, tooltip="Paste result"),
    ResultActionSpec(
        slot_id="archive",
        icon=ARCHIVE_ICON,
        tooltip="Archive result",
        active_icon=CHECK_ICON,
        active_tooltip="Archive accepted",
        active_color="#00B04F",
        active_hover_color="#00B04F",
    ),
    ResultActionSpec(
        slot_id="follow_up",
        icon=FOLLOW_UP_ICON,
        tooltip="Ask follow-up",
        active_tooltip="Close follow-up",
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
        self.root.grid_rowconfigure(3, weight=1)
        self._action_buttons: dict[str, ctk.CTkButton] = {}
        self._action_tooltips: dict[str, _Tooltip] = {}
        self.follow_up_visible = False
        self._build()

    def _build(self) -> None:
        self.header = ctk.CTkFrame(self.root, fg_color=SURFACE_BG)
        self.header.grid(row=0, column=0, sticky="ew", padx=9, pady=(3, 0))
        self.header.grid_columnconfigure(0, weight=1)

        title_area = ctk.CTkFrame(self.header, fg_color=SURFACE_BG)
        title_area.grid(row=0, column=0, sticky="w")
        self.title_label = ctk.CTkLabel(
            title_area,
            text="",
            font=ctk.CTkFont(family=TC_FONT_FAMILY, size=10, weight="bold"),
            text_color=TITLE_COLOR,
            wraplength=330,
        )
        self.title_label.pack(anchor="w")

        self.window_actions = ctk.CTkFrame(self.header, fg_color=SURFACE_BG)
        self.window_actions.grid(row=0, column=1, sticky="ne")
        self.model_label = ctk.CTkLabel(
            self.window_actions,
            text="",
            font=ctk.CTkFont(family=TC_FONT_FAMILY, size=9),
            text_color=MODEL_COLOR,
        )
        self.model_label.pack(side="left", padx=(0, 10))
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
        self._pin_tooltip = _Tooltip(self.pin_button, "Keep open", self.dialog.lifecycle)
        self.dialog.enable_drag(self.header, title_area, self.title_label, self.model_label)

        self.actions = ctk.CTkFrame(self.root, fg_color=SURFACE_BG)
        self.actions.grid(row=1, column=0, sticky="w", padx=9, pady=(0, 0))
        self.standard_actions = StandardResultActions(self)

        self.source_label = ctk.CTkLabel(
            self.root,
            text="",
            anchor="w",
            justify="left",
            font=ctk.CTkFont(family=TC_FONT_FAMILY, size=8),
            text_color=ANALYZING_COLOR,
            wraplength=390,
        )
        self.source_label.grid(row=2, column=0, sticky="ew", padx=9, pady=(0, 2))

        self.content_text = ctk.CTkTextbox(
            self.root,
            fg_color=SURFACE_BG,
            border_width=0,
            border_spacing=0,
            corner_radius=0,
            wrap="word",
            font=ctk.CTkFont(family=TC_FONT_FAMILY, size=12),
            text_color=CONTENT_COLOR,
            scrollbar_button_color="#4A4A4A",
            scrollbar_button_hover_color="#5A5A5A",
            height=170,
            pady=0,
        )
        self.content_text.grid(row=3, column=0, sticky="nsew", padx=9, pady=(0, 9))
        self.content_text.tag_config("heading", foreground=CONTENT_COLOR)
        self.content_text.tag_config("body", foreground=CONTENT_COLOR)
        self.content_text.tag_config("loading", foreground=ANALYZING_COLOR)

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
            font=ctk.CTkFont(family=TC_FONT_FAMILY, size=10),
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
            font=ctk.CTkFont(family=TC_FONT_FAMILY, size=10),
        )
        self.follow_send_button.grid(row=0, column=1, sticky="e")

    def set_title(self, title: str) -> None:
        self.title_label.configure(text=title)

    def set_source_preview(self, text: str) -> None:
        self.source_label.configure(text=text)

    def set_model(self, model: str) -> None:
        self.model_label.configure(text=f"model: {model}")

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

    def set_speaker_active(self, active: bool) -> None:
        self.standard_actions.set_speaker_active(active)

    def set_follow_up_active(self, active: bool) -> None:
        self.standard_actions.set_follow_up_active(active)

    def set_standard_action_enabled(self, slot_id: ResultActionId, enabled: bool) -> None:
        self.standard_actions.set_enabled(slot_id, enabled)

    def pulse_standard_action(self, slot_id: ResultActionId, duration_ms: int = 1000) -> None:
        self.standard_actions.pulse(slot_id, duration_ms)

    def add_action_slot(
        self,
        slot_id: str,
        label: str,
        command: Callable[[], None] | None,
        *,
        width: int,
        tooltip: str | None = None,
        text_color: str = CONTENT_COLOR,
    ) -> ctk.CTkButton:
        button = ctk.CTkButton(
            self.actions,
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
            self.content_text.insert("end", text, tag)
        self.content_text.configure(state="disabled")

    def selected_text(self) -> str | None:
        try:
            selected = self.content_text.get("sel.first", "sel.last").strip()
        except (tk.TclError, AttributeError):
            return None
        return selected or None

    def set_pinned_state(self, pinned: bool) -> None:
        self.dialog.set_pinned(pinned)
        self.pin_button.configure(
            text=UNPIN_ICON if pinned else PIN_ICON,
            fg_color=ACTION_HOVER_COLOR if pinned else SURFACE_BG,
            hover_color="#2F8DCE" if pinned else "#3A3A3A",
            text_color=CONTENT_COLOR if pinned else "#8A8A8A",
        )
        self._pin_tooltip.set_text("Unpin" if pinned else "Keep open")

    def toggle_pin(self) -> bool:
        pinned = self.dialog.toggle_pin()
        self.set_pinned_state(pinned)
        return pinned

    def show_follow_up(self, initial_text: str = "") -> None:
        if not self.follow_up_visible:
            self.follow_row.grid(row=4, column=0, sticky="ew", padx=10, pady=(0, 10))
            self.follow_up_visible = True
        if initial_text:
            self.follow_entry.delete(0, "end")
            self.follow_entry.insert(0, initial_text)
        self.dialog.lifecycle.focus(self.follow_entry)

    def hide_follow_up(self) -> None:
        if self.follow_up_visible:
            self.follow_row.grid_forget()
            self.follow_up_visible = False
