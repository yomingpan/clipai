from __future__ import annotations

from typing import Optional

import customtkinter as ctk

from clipai.ui.base_dialog import BaseDialog


def show_rescue_center(title="ClipAI Rescue Center") -> Optional[str]:
    """Small rescue menu near the cursor."""
    base = BaseDialog(title=title, width=220, height=90, position="cursor")
    if not base.is_valid():
        return None

    result = {"choice": None}

    btn_frame = ctk.CTkFrame(base.main_frame, fg_color="transparent")
    btn_frame.pack(fill="both", expand=True, padx=12, pady=8)

    def choose(value):
        result["choice"] = value
        base.lifecycle.close()

    def on_cancel(event=None):
        base.lifecycle.close()

    buttons = [("Think", "brain"), ("Save Time", "time"), ("Speak", "speak")]
    for label, value in buttons:
        btn = ctk.CTkButton(
            btn_frame,
            text=label,
            width=60,
            height=36,
            command=lambda v=value: choose(v),
        )
        btn.pack(side="left", padx=4)

    base.lifecycle.setup_close_on_escape(on_cancel)
    base.lifecycle.setup_force_focus(delay_ms=100)
    base.lifecycle.run_dialog()
    return result["choice"]
