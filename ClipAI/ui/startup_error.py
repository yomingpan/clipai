from __future__ import annotations

import sys


def show_startup_error(message: str) -> None:
    print(f"[clipai] Startup failed: {message}", file=sys.stderr)
    try:
        from tkinter import messagebox

        messagebox.showerror("ClipAI could not start", message)
    except Exception:
        pass
