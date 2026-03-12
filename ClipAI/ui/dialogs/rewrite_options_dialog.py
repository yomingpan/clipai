from __future__ import annotations

from typing import Optional

import customtkinter as ctk

from clipai.ui.base_dialog import BaseDialog


def get_rewrite_options(title="ClipAI - Rewrite Options") -> Optional[str]:
    """Small, low-distraction picker near the cursor."""
    base = BaseDialog(title=title, width=240, height=140, position="cursor")
    if not base.is_valid():
        return None

    result = {"tone": "neutral", "length": "shorter", "confirmed": False}

    tone_frame = ctk.CTkFrame(base.main_frame, fg_color="transparent")
    tone_frame.pack(fill="x", padx=12, pady=(8, 4))

    length_frame = ctk.CTkFrame(base.main_frame, fg_color="transparent")
    length_frame.pack(fill="x", padx=12, pady=(0, 8))

    def on_cancel(event=None):
        base.lifecycle.close()

    def confirm_with_tone(tone):
        result["tone"] = tone
        result["confirmed"] = True
        base.lifecycle.close()

    def toggle_length():
        result["length"] = "longer" if result["length"] == "shorter" else "shorter"
        length_btn.configure(text=f"Length: {result['length']}")

    for tone in ["neutral", "friendly", "formal"]:
        btn = ctk.CTkButton(
            tone_frame,
            text=tone.title(),
            width=60,
            height=28,
            command=lambda t=tone: confirm_with_tone(t),
        )
        btn.pack(side="left", padx=4)

    length_btn = ctk.CTkButton(
        length_frame,
        text="Length: shorter",
        width=110,
        height=28,
        fg_color="transparent",
        border_width=1,
        command=toggle_length,
    )
    length_btn.pack(side="left", padx=4)

    hint = ctk.CTkLabel(
        length_frame,
        text="Esc to cancel",
        font=("Microsoft JhengHei", 10),
        text_color=("gray30", "#A0A0A0"),
    )
    hint.pack(side="right", padx=4)

    base.lifecycle.setup_close_on_escape(on_cancel)
    base.lifecycle.setup_force_focus(delay_ms=100)
    base.lifecycle.run_dialog()

    if not result["confirmed"]:
        return None
    return f"Tone: {result['tone']}\nLength: {result['length']}"
