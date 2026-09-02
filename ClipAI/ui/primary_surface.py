from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import tkinter as tk
from typing import Protocol
import uuid

import customtkinter as ctk
from customtkinter.windows.widgets.scaling.scaling_tracker import ScalingTracker

from ClipAI.core.models import PopupBounds
from ClipAI.core.ports import NativeWindowSurface
from ClipAI.ui.dialog_lifecycle import DialogLifecycle
from ClipAI.ui.popup_layout import popup_bounds_from_tk_geometry
from ClipAI.ui.window_drag import WindowDragController


@dataclass(frozen=True)
class PrimarySurfaceLease:
    value: str


@dataclass(frozen=True)
class PrimarySurfaceSpec:
    bounds: PopupBounds
    title: str = "ClipAI"
    minimum_width: int = 340
    minimum_height: int = 220
    background_color: str = "#111111"
    frameless: bool = True
    transparent_background: bool = True
    topmost: bool = True
    hide_from_task_switcher: bool = True


class PrimarySurfaceView(Protocol):
    def mount_primary_content(self) -> bool: ...

    def unmount_primary_content(self) -> None: ...


def resample_window_dpi_scaling(window: tk.Misc) -> None:
    """Refresh CustomTkinter's per-window scale after initial placement."""
    previous_scaling = ScalingTracker.window_dpi_scaling_dict[window]
    ScalingTracker.window_dpi_scaling_dict[window] = (
        ScalingTracker.get_window_dpi_scaling(window)
    )
    try:
        ScalingTracker.update_scaling_callbacks_for_window(window)
    except Exception:
        ScalingTracker.window_dpi_scaling_dict[window] = previous_scaling
        raise


class PrimarySurfaceHost:
    """Own one native shell and identity-matched mounted content transitions."""

    def __init__(
        self,
        master: tk.Misc,
        spec: PrimarySurfaceSpec,
        native_window_surface: NativeWindowSurface | None,
        *,
        window_factory: Callable[[tk.Misc], tk.Misc] = ctk.CTkToplevel,
        dpi_resampler: Callable[[tk.Misc], None] = resample_window_dpi_scaling,
    ) -> None:
        self._native_window_surface = native_window_surface
        self._window = window_factory(master)
        self._lifecycle = DialogLifecycle(
            self._window,
            owns_mainloop=False,
            window_activator=self._activate_native_window,
        )
        self._leases: set[PrimarySurfaceLease] = set()
        self._mounted: tuple[PrimarySurfaceLease, PrimarySurfaceView] | None = None
        self._restore_target: tuple[PrimarySurfaceLease, PrimarySurfaceView] | None = None
        self._closed = False
        self._drag_controller = WindowDragController(self._window)

        window = self._window
        bounds = spec.bounds
        window.withdraw()
        window.title(spec.title)
        window.geometry(
            f"{bounds.width}x{bounds.height}+{bounds.x}+{bounds.y}"
        )
        window.minsize(spec.minimum_width, spec.minimum_height)
        window.configure(fg_color=spec.background_color)
        if spec.frameless:
            window.overrideredirect(True)
        if spec.transparent_background:
            try:
                window.attributes("-transparentcolor", spec.background_color)
            except Exception:
                pass
        if spec.topmost:
            window.attributes("-topmost", True)
        window.update_idletasks()
        dpi_resampler(window)
        if spec.hide_from_task_switcher:
            window.after_idle(self.hide_from_task_switcher)

    @property
    def window(self) -> tk.Misc:
        return self._window

    @property
    def lifecycle(self) -> DialogLifecycle:
        return self._lifecycle

    @property
    def is_closed(self) -> bool:
        return self._closed or self._lifecycle.is_closed

    def acquire(self) -> PrimarySurfaceLease:
        if self.is_closed:
            raise RuntimeError("primary surface is closed")
        lease = PrimarySurfaceLease(uuid.uuid4().hex)
        self._leases.add(lease)
        return lease

    def mount(self, lease: PrimarySurfaceLease, view: PrimarySurfaceView) -> bool:
        if not self._accepts(lease) or self._mounted is not None:
            return False
        try:
            mounted = view.mount_primary_content()
        except Exception:
            mounted = False
        if not mounted:
            return False
        self._mounted = (lease, view)
        return True

    def is_mounted(self, lease: PrimarySurfaceLease) -> bool:
        return self._mounted is not None and self._mounted[0] == lease

    def replace(
        self,
        active_lease: PrimarySurfaceLease,
        replacement_lease: PrimarySurfaceLease,
        replacement: PrimarySurfaceView,
    ) -> bool:
        if not self._accepts(replacement_lease):
            return False
        current = self._mounted
        if current is None or current[0] != active_lease:
            return False
        current[1].unmount_primary_content()
        try:
            mounted = replacement.mount_primary_content()
        except Exception:
            mounted = False
        if not mounted:
            current[1].mount_primary_content()
            return False
        self._restore_target = current
        self._mounted = (replacement_lease, replacement)
        return True

    def restore(self, active_lease: PrimarySurfaceLease) -> bool:
        current = self._mounted
        previous = self._restore_target
        if current is None or current[0] != active_lease or previous is None:
            return False
        current[1].unmount_primary_content()
        try:
            restored = previous[1].mount_primary_content()
        except Exception:
            restored = False
        if not restored:
            current[1].mount_primary_content()
            return False
        self._mounted = previous
        self._restore_target = None
        return True

    def show(self, lease: PrimarySurfaceLease) -> bool:
        if self._mounted is None or self._mounted[0] != lease:
            return False
        try:
            self._window.update_idletasks()
            self._window.deiconify()
        except tk.TclError:
            return False
        return True

    def current_bounds(self) -> PopupBounds | None:
        try:
            self._window.update_idletasks()
            return popup_bounds_from_tk_geometry(str(self._window.geometry()))
        except (AttributeError, TypeError, ValueError, tk.TclError):
            return None

    def bind_drag(self, *handles: object) -> None:
        self._drag_controller.bind(*handles)

    def resize(
        self,
        width: int,
        height: int,
        *,
        x: int | None = None,
        y: int | None = None,
    ) -> None:
        bounds = self.current_bounds()
        target_x = x if x is not None else (bounds.x if bounds is not None else 0)
        target_y = y if y is not None else (bounds.y if bounds is not None else 0)
        self._window.geometry(f"{width}x{height}+{target_x}+{target_y}")

    def close(self, lease: PrimarySurfaceLease | None = None) -> bool:
        if lease is not None and (
            self._mounted is None or self._mounted[0] != lease
        ):
            return False
        if self.is_closed:
            return False
        self._closed = True
        self._lifecycle.close()
        self._leases.clear()
        self._mounted = None
        self._restore_target = None
        return True

    def apply_visibility(self, visibility: str) -> bool:
        if visibility == "hidden":
            try:
                self._window.withdraw()
            except tk.TclError:
                return False
            return True
        if visibility == "visible_activate":
            try:
                self._window.deiconify()
            except tk.TclError:
                return False
            return self._lifecycle.focus()
        if visibility == "visible_no_activate":
            try:
                self._window.deiconify()
                child_id = self._toolkit_child_id()
            except (AttributeError, TypeError, ValueError, tk.TclError):
                return False
            native = self._native_window_surface
            return native.show_without_activation(child_id) if native is not None else False
        raise ValueError(f"unsupported popup visibility: {visibility}")

    def owns_foreground(self) -> bool:
        native = self._native_window_surface
        if native is None:
            return False
        try:
            return native.owns_foreground(self._toolkit_child_id())
        except (AttributeError, TypeError, ValueError, tk.TclError):
            return False

    def hide_from_task_switcher(self) -> bool:
        native = self._native_window_surface
        if native is None:
            return False
        try:
            return native.hide_from_task_switcher(self._toolkit_child_id())
        except (AttributeError, TypeError, ValueError, tk.TclError):
            return False

    def _accepts(self, lease: PrimarySurfaceLease) -> bool:
        return not self.is_closed and lease in self._leases

    def _toolkit_child_id(self) -> int:
        self._window.update_idletasks()
        return int(self._window.winfo_id())

    def _activate_native_window(self, window: tk.Misc) -> bool:
        native = self._native_window_surface
        if native is None:
            return False
        try:
            window.deiconify()
            return native.activate(self._toolkit_child_id())
        except (AttributeError, TypeError, ValueError, tk.TclError):
            return False
