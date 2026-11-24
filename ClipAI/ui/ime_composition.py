from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont

from ClipAI.core.ports import NativeWindowSurface


_FALLBACK_FAMILY = "Microsoft JhengHei UI"


def install_ime_composition_font(
    widget: object,
    surface: NativeWindowSurface | None,
) -> None:
    """Keep native IME composition text aligned with the toolkit font."""
    if surface is None:
        return
    inner = getattr(widget, "_entry", None) or getattr(widget, "_textbox", None) or widget

    def apply(_event=None) -> None:
        try:
            resolved = tkfont.Font(root=inner, font=inner.cget("font"))
            actual = resolved.actual()
            family = str(actual.get("family") or _FALLBACK_FAMILY)
            size = int(actual.get("size") or 0)
            if size > 0:
                size = -int(round(float(inner.winfo_fpixels(f"{size}p"))))
            toolkit_child_id = int(widget.winfo_toplevel().winfo_id())
            surface.set_ime_composition_font(
                toolkit_child_id,
                family=family,
                height=size,
                weight=700 if actual.get("weight") == "bold" else 400,
                italic=actual.get("slant") == "italic",
            )
        except (AttributeError, TypeError, ValueError, tk.TclError):
            return

    try:
        inner.bind("<FocusIn>", apply, add="+")
    except (AttributeError, tk.TclError):
        return
