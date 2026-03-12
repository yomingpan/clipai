from __future__ import annotations

from typing import Dict, Optional

import customtkinter as ctk
import tkinter as tk

from clipai.ui.memory_indicator import MemoryIndicator
from clipai.ui.base_dialog import BaseDialog


def get_user_input(title="ClipAI Input", prompt_text="Enter additional context (Espanso templates supported):"):
    """
    Opens a modern CustomTkinter dialog to get user input.
    """
    base = BaseDialog(title=title, width=550, height=350, position="center")
    if not base.is_valid():
        return None

    result: Dict[str, Optional[str]] = {"text": None}

    from clipai import memory_manager

    ttl_enabled = memory_manager.get_auto_memory_ttl() > 0
    has_auto = memory_manager.get_auto_count() > 0
    has_manual = memory_manager.get_manual_count() > 0
    should_glow = ttl_enabled and has_auto

    header_frame = ctk.CTkFrame(base.main_frame, fg_color="transparent", height=36)
    header_frame.pack(fill="x", padx=12, pady=(10, 0))
    header_frame.pack_propagate(False)

    indicator = MemoryIndicator(
        header_frame,
        base.root,
        base.pending_tasks,
        has_auto=has_auto,
        has_manual=has_manual,
        should_glow=should_glow,
        lifecycle=base.lifecycle,
        canvas_size=32,
        core_radius=6,
        glow_base=11.0,
        glow_amplitude=3.0,
        empty_radius=4,
    )
    indicator.canvas.pack(side="left", padx=(0, 5), pady=4)
    indicator.start()

    title_label = ctk.CTkLabel(
        header_frame,
        text=title,
        font=("Microsoft JhengHei", 12, "bold"),
        text_color="#3B8ED0",
        anchor="w",
    )
    title_label.pack(side="left", fill="y")

    label = ctk.CTkLabel(
        base.main_frame,
        text=prompt_text,
        font=("Microsoft JhengHei", 13),
    )
    label.pack(pady=(5, 5), padx=12, anchor="w")

    def on_submit(event=None):
        result["text"] = text_area.get("1.0", "end-1c").strip()
        base.lifecycle.close()

    def on_cancel(event=None):
        base.lifecycle.close()

    btn_frame = ctk.CTkFrame(base.main_frame, fg_color="transparent")
    btn_frame.pack(side="bottom", fill="x", padx=12, pady=12)

    cancel_btn = ctk.CTkButton(
        btn_frame,
        text="Cancel (Esc)",
        command=on_cancel,
        width=90,
        fg_color="transparent",
        border_width=1,
        text_color=("gray10", "#DCE4EE"),
    )
    cancel_btn.pack(side="left")

    submit_btn = ctk.CTkButton(
        btn_frame,
        text="Submit (Ctrl+Enter)",
        command=on_submit,
        width=160,
        font=("Microsoft JhengHei", 12, "bold"),
        fg_color="#3B8ED0",
        hover_color="#2B6E9E",
    )
    submit_btn.pack(side="right")

    text_container = ctk.CTkFrame(base.main_frame, corner_radius=8, border_width=1)
    text_container.pack(fill="both", expand=True, padx=12, pady=5)

    text_area = tk.Text(
        text_container,
        font=("Microsoft JhengHei", 11),
        undo=True,
        padx=10,
        pady=10,
        borderwidth=0,
        highlightthickness=0,
        bg=base.root._apply_appearance_mode(ctk.ThemeManager.theme["CTkTextbox"]["fg_color"]),
        fg=base.root._apply_appearance_mode(ctk.ThemeManager.theme["CTkTextbox"]["text_color"]),
        insertbackground=base.root._apply_appearance_mode(ctk.ThemeManager.theme["CTkTextbox"]["text_color"]),
        wrap="word",
    )
    text_area.pack(fill="both", expand=True, padx=2, pady=2)
    text_area.focus_set()

    base.root.bind("<Control-Return>", on_submit)
    base.lifecycle.setup_close_on_escape(on_cancel)
    base.lifecycle.setup_close_on_focus_out(delay_ms=100, callback=on_cancel)
    base.lifecycle.setup_force_focus(target_widget=text_area, delay_ms=300)

    from clipai.core.event_bus import Events, get_event_bus

    bus = get_event_bus()
    bus.set_tk_root(base.root)

    def _on_pipeline_update(content, action_id, **kwargs):
        try:
            if not base.root.winfo_exists():
                return
            if content and isinstance(content, str):
                title_label.configure(text=f"ClipAI - {action_id} (Updated)")
                text_area.delete("1.0", "end")
                text_area.insert("1.0", content)
                print(f"[clipai] Input Dialog Updated via Pipeline Mode: {action_id}")
        except (tk.TclError, RuntimeError):
            pass

    pipeline_cb = bus.subscribe(Events.PIPELINE_UPDATE, _on_pipeline_update)
    base.lifecycle.add_event_subscription(Events.PIPELINE_UPDATE, pipeline_cb)

    base.lifecycle.run_dialog()
    return result["text"]
