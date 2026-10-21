"""One nonactivating Inline Dictation surface; semantic state arrives as a view."""

from collections.abc import Callable
from dataclasses import dataclass
import tkinter as tk
import customtkinter as ctk

from PIL import Image, ImageTk

from ClipAI.core.models import DisplayMetrics, InlineDictationPlacement
from ClipAI.core.ports import DisplayMetricsReader, NativeWindowSurface
from ClipAI.core.voice import InlineDictationView
from ClipAI.ui import voice_visuals as visuals
from ClipAI.ui.dialog_lifecycle import DialogLifecycle


@dataclass(frozen=True)
class PillLayout:
    x: int
    y: int
    width: int
    height: int
    pill_x: int
    pill_y: int
    panel_above: bool
    scale: float


def resolve_pill_layout(metrics: DisplayMetrics, placement: InlineDictationPlacement) -> PillLayout:
    scale = max(.1, metrics.scale)
    width = round(visuals.CANVAS_WIDTH*scale)
    pill_height, strip_height, panel_height = (round(value*scale) for value in (visuals.BASE_HEIGHT, visuals.STRIP_HEIGHT, visuals.PANEL_HEIGHT))
    height = pill_height+strip_height+panel_height
    margin = round(visuals.MARGIN*scale)
    pill_x = round((visuals.CANVAS_WIDTH-visuals.BASE_WIDTH)*scale/2)
    above = placement == "bottom_center" or metrics.cursor_y > metrics.work_y+metrics.work_height/2
    pill_y = panel_height+strip_height if above else 0
    requested_x = metrics.work_x+(metrics.work_width-width)//2 if placement == "bottom_center" else metrics.cursor_x+round(14*scale)-pill_x
    requested_y = metrics.work_y+metrics.work_height-margin-height if placement == "bottom_center" else metrics.cursor_y+round(18*scale)-pill_y
    left, top = metrics.work_x+margin, metrics.work_y+margin
    x = min(max(requested_x, left), max(left, metrics.work_x+metrics.work_width-width-margin))
    y = min(max(requested_y, top), max(top, metrics.work_y+metrics.work_height-height-margin))
    return PillLayout(x, y, width, height, pill_x, pill_y, above, scale)


class InlinePill:
    def __init__(
        self, root: tk.Misc, *, interaction_id: str,
        on_confirm: Callable[[bool], None], on_cancel: Callable[[], None],
        on_copy: Callable[[], None] = lambda: None,
        native_window_surface: NativeWindowSurface | None = None,
        display_metrics: DisplayMetricsReader | None = None,
        placement: InlineDictationPlacement = "bottom_center",
    ) -> None:
        self.interaction_id = interaction_id
        self._on_confirm, self._on_cancel, self._on_copy = on_confirm, on_cancel, on_copy
        self._native = native_window_surface
        self._metrics = display_metrics
        self._placement = placement
        self._view = InlineDictationView(interaction_id)
        self._layout: PillLayout | None = None
        self._backdrop: Image.Image | None = None
        self._photo: ImageTk.PhotoImage | None = None
        self._shown = False
        self._frame = 0
        self._frame_job: str | None = None
        self._click_locked_phase: str | None = None
        self._hover = ""
        self._panel: tk.Frame | None = None
        self._panel_signature: tuple[str, str, str] | None = None
        self._panel_photo: ImageTk.PhotoImage | None = None
        self._window = tk.Toplevel(root)
        self._window.withdraw()
        self._window.overrideredirect(True)
        self._window.attributes("-topmost", True)
        self._window.configure(bg=visuals.TRANSPARENT_KEY)
        self._window.attributes("-transparentcolor", visuals.TRANSPARENT_KEY)
        self._lifecycle = DialogLifecycle(self._window, owns_mainloop=False)
        self._canvas = tk.Canvas(self._window, bg=visuals.TRANSPARENT_KEY, highlightthickness=0, bd=0)
        self._canvas.pack(fill="both", expand=True)
        self._canvas.bind("<Button-1>", self._click)
        self._canvas.bind("<Motion>", self._motion)
        self._canvas.bind("<Leave>", lambda _event: self._set_hover(""))
        self._status = tk.Label(self._window, bg=visuals.BODY, fg=visuals.CONFIRM, bd=0)
        self._center = tk.Label(self._window, bg=visuals.BODY, bd=0)

    def show(self) -> None:
        if self._lifecycle.is_closed or self._shown:
            return
        if self._metrics is not None:
            metrics = self._metrics.current()
        else:
            x, y = self._window.winfo_pointerxy()
            metrics = DisplayMetrics(1, 0, 0, self._window.winfo_screenwidth(), self._window.winfo_screenheight(), x, y)
        self._layout = layout = resolve_pill_layout(metrics, self._placement)
        self._window.geometry(f"{layout.width}x{layout.height}{layout.x:+d}{layout.y:+d}")
        if self._native is not None:
            rgb = self._native.capture_screen_rgb(layout.x, layout.y, layout.width, layout.height)
            if rgb is not None:
                self._backdrop = Image.frombytes("RGB", (layout.width, layout.height), rgb)
        self._draw()
        self._window.deiconify()
        # Tk materializes/replaces the native wrapper during mapping. Apply
        # native activation policy only after that wrapper has settled.
        self._window.update_idletasks()
        if self._native is not None:
            self._native.show_without_activation(self._window.winfo_id())
            self._native.prevent_click_activation(self._window.winfo_id())
        self._shown = True
        self._sync_animation()

    def present(self, view: InlineDictationView) -> None:
        if self._lifecycle.is_closed or view.interaction_id != self.interaction_id:
            return
        if view.phase != self._view.phase:
            self._click_locked_phase = None
        self._view = view
        if self._shown:
            self._draw()
            self._sync_animation()

    def _draw(self) -> None:
        layout = self._layout
        if layout is None:
            return
        width, height = round(visuals.BASE_WIDTH*layout.scale), round(visuals.BASE_HEIGHT*layout.scale)
        backdrop = self._backdrop.crop((layout.pill_x, layout.pill_y, layout.pill_x+width, layout.pill_y+height)) if self._backdrop is not None else None
        bitmap = visuals.draw_pill(self._view, scale=layout.scale, frame=self._frame, backdrop=backdrop, hover=self._hover)
        self._photo = ImageTk.PhotoImage(bitmap, master=self._window)
        self._canvas.delete("pill")
        self._canvas.create_image(layout.pill_x, layout.pill_y, image=self._photo, anchor="nw", tags="pill")
        visual = visuals.project_inline_visuals(self._view, hover=self._hover)
        self._status.configure(text=visual.status, font=("Microsoft JhengHei", -max(1, round(9*layout.scale))))
        strip_y = layout.pill_y-round(visuals.STRIP_HEIGHT*layout.scale) if layout.panel_above else layout.pill_y+height
        self._status.place(x=layout.width//2, y=strip_y, anchor="n", height=round(visuals.STRIP_HEIGHT*layout.scale))
        if visual.center_text:
            self._center.configure(text=visual.center_text, fg=visuals.AMBER if self._view.countdown_seconds is not None else visuals.MUTED, font=("Microsoft JhengHei", -max(1, round(9*layout.scale))))
            self._center.place(x=layout.pill_x+round(visuals.WAVE_CENTER*layout.scale), y=layout.pill_y+round(visuals.CENTER_Y*layout.scale), anchor="center", width=round(visuals.WAVE_WIDTH*layout.scale), height=round(16*layout.scale))
        else:
            self._center.place_forget()
        self._sync_panel(visual)

    def _sync_panel(self, visual: visuals.InlineVisuals) -> None:
        layout = self._layout
        assert layout is not None
        visible = self._view.phase in {"awaiting", "recovery", "cancel_unconfirmed"} or self._view.phase == "closed" and bool(self._view.message)
        signature = (self._view.text, visual.panel_message, visual.panel_hint) if visible else None
        if signature != self._panel_signature:
            if self._panel is not None:
                self._panel.destroy()
                self._panel = None
            self._canvas.delete("panel")
            self._panel_photo = None
            self._panel_signature = signature
            if visible:
                scale = layout.scale
                top = 0 if layout.panel_above else round(visuals.BASE_HEIGHT*scale)+round(visuals.STRIP_HEIGHT*scale)
                height = round(visuals.PANEL_HEIGHT*scale)
                backdrop = self._backdrop.crop((0, top, layout.width, top+height)) if self._backdrop is not None else None
                self._panel_photo = ImageTk.PhotoImage(visuals.draw_panel(scale=scale, backdrop=backdrop), master=self._window)
                self._canvas.create_image(0, top, image=self._panel_photo, anchor="nw", tags="panel")
                panel = self._panel = tk.Frame(self._window, bg=visuals.BODY)
                panel.place(x=round(10*scale), y=top+round(10*scale), width=round(280*scale), height=height-round(20*scale))
                if visual.panel_message:
                    tk.Label(panel, text=visual.panel_message, wraplength=round(280*scale), justify="left", anchor="w", bg=visuals.BODY, fg=visuals.AMBER if self._view.phase in {"recovery", "closed"} else visuals.MESSAGE_COLOR, font=("Microsoft JhengHei", -max(1, round(9*scale)))).pack(fill="x")
                tk.Label(panel, text=visual.panel_hint, bg=visuals.BODY, fg=visuals.CONFIRM, font=("Microsoft JhengHei", -max(1, round(9*scale)))).pack(fill="x")
                controls = tk.Frame(panel, bg=visuals.BODY)
                controls.pack(side="bottom", fill="x")
                self._copy_button = ctk.CTkButton(controls, text="複製", width=44, height=20, corner_radius=10, command=self._on_copy, fg_color=visuals.BUTTON, hover_color=visuals.OUTLINE, font=ctk.CTkFont(size=10))
                self._copy_button.pack(side="left")
                self._copy_status = tk.Label(controls, bg=visuals.BODY, fg=visuals.CONFIRM, font=("Microsoft JhengHei", -max(1, round(9*scale))))
                self._copy_status.pack(side="left", padx=round(5*scale))
                content = tk.Frame(panel, bg=visuals.BODY)
                content.pack(fill="both", expand=True)
                self._text = tk.Text(content, height=4 if visual.panel_message else 6, width=1, wrap="word", relief="flat", bd=0, bg=visuals.BODY, fg=visuals.WHITE, font=("Microsoft JhengHei", -max(1, round(11*scale))))
                self._text.insert("1.0", self._view.text)
                self._text.configure(state="disabled")
                scrollbar = tk.Scrollbar(content, command=self._text.yview)
                scrollbar.pack(side="right", fill="y")
                self._text.configure(yscrollcommand=scrollbar.set)
                self._text.pack(fill="both", expand=True)
                if self._view.phase == "closed":
                    controls.pack_forget()
        if self._panel is not None:
            self._copy_button.configure(state="disabled" if self._view.copy_state == "pending" else "normal")
            self._copy_status.configure(text=visual.copy_label)

    def _sync_animation(self) -> None:
        view = self._view
        animate = visuals.project_inline_visuals(view).spinner is not None or view.phase == "listening" and not view.silence_detected and view.audio_level > .002
        if not animate and self._frame_job is not None:
            self._lifecycle.cancel(self._frame_job)
            self._frame_job = None
        if animate and self._frame_job is None and self._shown:
            self._frame_job = self._lifecycle.schedule(visuals.FRAME_MS, self._tick)

    def _tick(self) -> None:
        self._frame_job = None
        self._frame += 1
        self._draw()
        self._sync_animation()

    def _hit(self, x: int, y: int) -> str:
        layout = self._layout
        if layout is None:
            return ""
        x, y = (x-layout.pill_x)/layout.scale, (y-layout.pill_y)/layout.scale
        radius = visuals.REFINE_DIAMETER/2+visuals.HIT_PADDING
        if abs(y-visuals.CENTER_Y) > radius:
            return ""
        for kind, center in visuals.BUTTON_CENTERS:
            if abs(x-center) <= radius:
                return kind
        return ""

    def _click(self, event: tk.Event) -> str:
        kind = self._hit(event.x, event.y)
        if self._click_locked_phase is not None or not kind:
            return "break"
        if kind == "cancel":
            self._click_locked_phase = self._view.phase
            self._on_cancel()
        elif self._view.phase in {"starting", "listening", "awaiting"} and (kind == "raw" or self._view.allow_refine):
            self._click_locked_phase = self._view.phase
            self._on_confirm(kind == "refine")
        return "break"

    def _motion(self, event: tk.Event) -> None:
        self._set_hover(self._hit(event.x, event.y))

    def _set_hover(self, hover: str) -> None:
        if hover != self._hover:
            self._hover = hover
            self._draw()

    def close(self) -> None:
        self._backdrop = None
        self._photo = None
        self._panel_photo = None
        self._frame_job = None
        self._lifecycle.close()
