from __future__ import annotations

import tkinter as tk


def attach_tooltip(widget, text: str) -> None:
    tooltip = {"window": None}

    def _show(event=None) -> None:
        del event
        if tooltip["window"] is not None:
            return
        x = widget.winfo_rootx() + 10
        y = widget.winfo_rooty() + widget.winfo_height() + 8

        window = tk.Toplevel(widget)
        window.wm_overrideredirect(True)
        window.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            window,
            text=text,
            bg="#1C2230",
            fg="#F4F7FB",
            padx=8,
            pady=4,
            font=("Microsoft JhengHei", 9),
            relief="solid",
            borderwidth=1,
        )
        label.pack()
        tooltip["window"] = window

    def _hide(event=None) -> None:
        del event
        if tooltip["window"] is not None:
            tooltip["window"].destroy()
            tooltip["window"] = None

    widget.bind("<Enter>", _show, add="+")
    widget.bind("<Leave>", _hide, add="+")
    widget.bind("<ButtonPress>", _hide, add="+")
