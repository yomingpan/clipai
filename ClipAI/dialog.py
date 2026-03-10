
import customtkinter as ctk
import tkinter as tk
import ctypes
from ctypes import wintypes
from typing import Optional, Dict, List, Any
import re
from clipai.ui.memory_indicator import MemoryIndicator
from clipai.ui.base_dialog import BaseDialog

# Set appearance mode and color theme globally to avoid Tcl errors on re-initialization
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

def get_user_input(title="ClipAI Input", prompt_text="Enter additional context (Espanso templates supported):"):
    """
    Opens a modern CustomTkinter dialog to get user input.
    """
    base = BaseDialog(title=title, width=550, height=350, position="center")
    if not base.is_valid():
        return None
    
    result: Dict[str, Optional[str]] = {"text": None}
    
    # Memory Indicator for Input Dialog
    from clipai import memory_manager
    ttl_enabled = memory_manager.get_auto_memory_ttl() > 0
    has_auto = memory_manager.get_auto_count() > 0
    has_manual = memory_manager.get_manual_count() > 0
    # Breathing glow only when TTL is enabled AND there is auto memory
    should_glow = ttl_enabled and has_auto

    header_frame = ctk.CTkFrame(base.main_frame, fg_color="transparent", height=36)
    header_frame.pack(fill="x", padx=12, pady=(10, 0))
    header_frame.pack_propagate(False)

    indicator = MemoryIndicator(
        header_frame, base.root, base.pending_tasks,
        has_auto=has_auto, has_manual=has_manual, should_glow=should_glow,
        lifecycle=base.lifecycle,
        canvas_size=32, core_radius=6, glow_base=11.0, glow_amplitude=3.0, empty_radius=4
    )
    indicator.canvas.pack(side="left", padx=(0, 5), pady=4)
    indicator.start()

    title_label = ctk.CTkLabel(
        header_frame,
        text=title,
        font=("Microsoft JhengHei", 12, "bold"),
        text_color="#3B8ED0",
        anchor="w"
    )
    title_label.pack(side="left", fill="y")

    label = ctk.CTkLabel(
        base.main_frame,
        text=prompt_text,
        font=("Microsoft JhengHei", 13)
    )
    label.pack(pady=(5, 5), padx=12, anchor="w")

    def on_submit(event=None):
        result["text"] = text_area.get("1.0", "end-1c").strip()
        base.lifecycle.close()

    def on_cancel(event=None):
        base.lifecycle.close()

    # Pack buttons at bottom first so text_container can expand into remaining space
    btn_frame = ctk.CTkFrame(base.main_frame, fg_color="transparent")
    btn_frame.pack(side="bottom", fill="x", padx=12, pady=12)

    cancel_btn = ctk.CTkButton(
        btn_frame,
        text="Cancel (Esc)",
        command=on_cancel,
        width=90,
        fg_color="transparent",
        border_width=1,
        text_color=("gray10", "#DCE4EE")
    )
    cancel_btn.pack(side="left")

    submit_btn = ctk.CTkButton(
        btn_frame,
        text="Submit (Ctrl+Enter)",
        command=on_submit,
        width=160,
        font=("Microsoft JhengHei", 12, "bold"),
        fg_color="#3B8ED0",
        hover_color="#2B6E9E"
    )
    submit_btn.pack(side="right")

    # Pack text container after buttons — it expands into remaining space
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
        wrap="word"
    )
    text_area.pack(fill="both", expand=True, padx=2, pady=2)
    text_area.focus_set()

    base.root.bind("<Control-Return>", on_submit)
    base.lifecycle.setup_close_on_escape(on_cancel)
    base.lifecycle.setup_close_on_focus_out(delay_ms=100, callback=on_cancel)
    base.lifecycle.setup_force_focus(target_widget=text_area, delay_ms=300)
    
    from clipai.core.event_bus import get_event_bus, Events
    
    # EventBus subscription replaces 500ms polling
    _bus = get_event_bus()
    _bus.set_tk_root(base.root)  # Enable UI-thread marshalling
    
    def _on_pipeline_update(content, action_id, **kwargs):
        """Handle pipeline updates reactively via EventBus."""
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
    
    _pipeline_cb = _bus.subscribe(Events.PIPELINE_UPDATE, _on_pipeline_update)
    base.lifecycle.add_event_subscription(Events.PIPELINE_UPDATE, _pipeline_cb)
    
    base.lifecycle.run_dialog()
    return result["text"]

def get_rewrite_options(title="ClipAI - Rewrite Options") -> Optional[str]:
    """
    Small, low-distraction picker near the mouse: 專業/口語/精煉/長一點.
    """
    base = BaseDialog(title=title, width=240, height=140, position="cursor")
    if not base.is_valid():
        return None

    result = {"tone": "專業", "length": "短一點", "confirmed": False}

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
        result["length"] = "長一點" if result["length"] == "短一點" else "短一點"
        length_btn.configure(text=f"長一點{' ✓' if result['length'] == '長一點' else ''}")

    for tone in ["專業", "口語", "精煉"]:
        btn = ctk.CTkButton(
            tone_frame,
            text=tone,
            width=60,
            height=28,
            command=lambda t=tone: confirm_with_tone(t)
        )
        btn.pack(side="left", padx=4)

    length_btn = ctk.CTkButton(
        length_frame,
        text="長一點",
        width=80,
        height=28,
        fg_color="transparent",
        border_width=1,
        command=toggle_length
    )
    length_btn.pack(side="left", padx=4)

    hint = ctk.CTkLabel(
        length_frame,
        text="按 Esc 取消",
        font=("Microsoft JhengHei", 10),
        text_color=("gray30", "#A0A0A0")
    )
    hint.pack(side="right", padx=4)

    base.lifecycle.setup_close_on_escape(on_cancel)
    base.lifecycle.setup_force_focus(delay_ms=100)
    base.lifecycle.run_dialog()

    if not result["confirmed"]:
        return None
    return f"語氣: {result['tone']}\n長度: {result['length']}"

def show_rescue_center(title="ClipAI Rescue Center") -> Optional[str]:
    """Small rescue menu near cursor with three choices: brain, time, speak."""
    base = BaseDialog(title=title, width=200, height=80, position="cursor")
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

    buttons = [("🧠", "brain"), ("⏰", "time"), ("🗣️", "speak")]
    for label, value in buttons:
        btn = ctk.CTkButton(
            btn_frame,
            text=label,
            width=48,
            height=36,
            command=lambda v=value: choose(v)
        )
        btn.pack(side="left", padx=4)

    base.lifecycle.setup_close_on_escape(on_cancel)
    base.lifecycle.setup_force_focus(delay_ms=100)
    base.lifecycle.run_dialog()
    return result["choice"]

def show_result_popup(text_or_gen, title="ClipAI Result", original_input="", tray=None, on_think_deep_click=None, tts_service=None, action_id="", rhythm_mode="steer", follow_up_placeholder=None):
    """
    Displays a non-blocking, borderless popup window near the mouse cursor.
    Supports both static text and a generator for streaming.

    Thin wrapper around ResultPopup — see clipai/ui/result_popup/popup.py for implementation.
    """
    from clipai.ui.result_popup.popup import ResultPopup

    popup = ResultPopup(
        text_or_gen=text_or_gen,
        title=title,
        original_input=original_input,
        tray=tray,
        on_think_deep_click=on_think_deep_click,
        tts_service=tts_service,
        action_id=action_id,
        rhythm_mode=rhythm_mode,
        follow_up_placeholder=follow_up_placeholder,
    )
    return popup.run()

def show_hotkey_guide(actions_list, title="ClipAI Hotkey Guide"):
    """
    Displays a clean, grouped hotkey reference panel.
    """
    from collections import OrderedDict
    
    groups: OrderedDict = OrderedDict()
    for act in actions_list:
        hotkey = act.get("hotkey")
        if not hotkey:
            continue
        group_name = act.get("group", "Other")
        groups.setdefault(group_name, []).append(act)

    row_height = 28
    group_header_height = 32
    total_rows = sum(len(items) for items in groups.values())
    total_groups = len(groups)
    content_height = 50 + total_groups * group_header_height + total_rows * row_height + 60
    window_width = 420
    window_height = min(max(content_height, 200), 700)

    base = BaseDialog(title=title, width=window_width, height=window_height, position="center")
    if not base.is_valid():
        return

    header_frame = ctk.CTkFrame(base.main_frame, fg_color="transparent", height=36)
    header_frame.pack(fill="x", padx=12, pady=(12, 4))
    header_frame.pack_propagate(False)

    title_label = ctk.CTkLabel(
        header_frame,
        text="⌨️  " + title,
        font=("Microsoft JhengHei", 12, "bold"),
        text_color="#3B8ED0",
        anchor="w"
    )
    title_label.pack(side="left", fill="y")

    # Pack footer at bottom first so scroll_frame can expand into remaining space
    footer_frame = ctk.CTkFrame(base.main_frame, fg_color="transparent")
    footer_frame.pack(side="bottom", fill="x", padx=12, pady=(4, 10))

    legend = ctk.CTkLabel(
        footer_frame,
        text="📋 Paste   🪟 Popup   🗣️ Speak   🧠 Memory",
        font=("Microsoft JhengHei", 10),
        text_color=("gray40", "gray55"),
        anchor="w",
    )
    legend.pack(side="left")

    close_hint = ctk.CTkLabel(
        footer_frame,
        text="Esc to close",
        font=("Microsoft JhengHei", 10),
        text_color=("gray50", "gray60"),
        anchor="e",
    )
    close_hint.pack(side="right")

    scroll_frame = ctk.CTkScrollableFrame(
        base.main_frame,
        fg_color="transparent",
        scrollbar_button_color=("#c0c0c0", "#555555"),
        scrollbar_button_hover_color=("#a0a0a0", "#777777"),
    )
    scroll_frame.pack(fill="both", expand=True, padx=12, pady=(0, 5))

    for group_name, items in groups.items():
        group_label = ctk.CTkLabel(
            scroll_frame,
            text=group_name,
            font=("Microsoft JhengHei", 12, "bold"),
            text_color=("#444444", "#BBBBBB"),
            anchor="w",
        )
        group_label.pack(fill="x", padx=8, pady=(10, 2))

        sep = ctk.CTkFrame(scroll_frame, height=1, fg_color=("#DDDDDD", "#444444"))
        sep.pack(fill="x", padx=8, pady=(0, 4))

        for act in items:
            row = ctk.CTkFrame(scroll_frame, fg_color="transparent")
            row.pack(fill="x", padx=8, pady=1)

            output_cfg = act.get("output", {})
            action_id = act.get("id", "")
            if action_id == "tts_speak":
                behavior_icon = "🗣️"
            elif action_id in ("memorize", "reset_memory"):
                behavior_icon = "🧠"
            elif output_cfg.get("show_popup", False):
                behavior_icon = "🪟"
            else:
                behavior_icon = "📋"

            display_name = f"{behavior_icon}  {act.get('name', act.get('id', '?'))}"
            name_label = ctk.CTkLabel(
                row,
                text=display_name,
                font=("Microsoft JhengHei", 11),
                anchor="w",
            )
            name_label.pack(side="left", fill="x", expand=True)

            hk_text = act["hotkey"].replace("alt+shift+", "Alt+Shift+").replace("alt+", "Alt+").replace("shift+", "Shift+")
            badge_frame = ctk.CTkFrame(
                row,
                fg_color=("#E8E8E8", "#3A3A3A"),
                corner_radius=4,
            )
            badge_frame.pack(side="right", padx=(4, 0))

            hk_label = ctk.CTkLabel(
                badge_frame,
                text=hk_text,
                font=("Consolas", 10),
                text_color=("#333333", "#CCCCCC"),
                padx=6,
                pady=2,
            )
            hk_label.pack()

    base.lifecycle.setup_close_on_escape()
    base.lifecycle.setup_close_on_focus_out()
    base.lifecycle.setup_force_focus(delay_ms=100)
    base.lifecycle.run_dialog()

def show_memory_confirmation(content_preview: str, memory_count: int, max_count: int = 5, on_undo=None):
    """
    Show a small, auto-dismissing toast near the cursor confirming a memorize action.
    """
    base = BaseDialog(title="ClipAI Memory", width=340, height=80, position="cursor", border_color="#3B8ED0", track_dialog_state=False)
    if not base.is_valid():
        return {"undone": False}

    result = {"undone": False}

    top_frame = ctk.CTkFrame(base.main_frame, fg_color="transparent")
    top_frame.pack(fill="x", padx=12, pady=(8, 2))

    if len(content_preview) > 40:
        content_preview = content_preview[:40] + "…"

    info_label = ctk.CTkLabel(
        top_frame,
        text=f"🧠 已記住 ({memory_count}/{max_count}): {content_preview}",
        font=("Microsoft JhengHei", 11),
        anchor="w",
    )
    info_label.pack(side="left", fill="x", expand=True)

    bottom_frame = ctk.CTkFrame(base.main_frame, fg_color="transparent")
    bottom_frame.pack(fill="x", padx=12, pady=(0, 6))

    def do_undo():
        result["undone"] = True
        if on_undo:
            on_undo()
        info_label.configure(text="↩️ 已撤回")
        undo_btn.configure(state="disabled", text="✓ Undone")
        base.lifecycle.schedule(800, base.lifecycle.close)

    def close_toast(event=None):
        base.lifecycle.close()

    undo_btn = ctk.CTkButton(
        bottom_frame,
        text="↩️ Undo",
        width=70,
        height=24,
        font=("Microsoft JhengHei", 10),
        fg_color="transparent",
        border_width=1,
        text_color=("gray10", "#DCE4EE"),
        command=do_undo,
    )
    undo_btn.pack(side="left")

    hint_label = ctk.CTkLabel(
        bottom_frame,
        text="3s 後自動關閉",
        font=("Microsoft JhengHei", 9),
        text_color=("gray50", "gray60"),
        anchor="e",
    )
    hint_label.pack(side="right")

    base.lifecycle.setup_close_on_escape(close_toast)
    base.lifecycle.schedule(3000, close_toast)
    base.lifecycle.setup_force_focus(delay_ms=100)
    base.lifecycle.run_dialog(track_dialog_state=False)
    return result

def show_memory_viewer(memory_data, on_unpin=None, on_clear_all=None, on_memorize=None,
                       clipboard_preview="", title="ClipAI Memory Context"):
    """
    Display a scrollable Memory Viewer panel showing all Pinned and Recent memories.
    """
    from datetime import datetime

    manual_items = memory_data.get("manual", [])
    auto_items = memory_data.get("auto", [])
    total = len(manual_items) + len(auto_items)
    has_clipboard = bool(clipboard_preview and clipboard_preview.strip())

    row_height = 52
    section_header_height = 36
    sections = (1 if manual_items else 0) + (1 if auto_items else 0)
    pin_section_height = 90 if has_clipboard and on_memorize else 0
    content_height = 60 + pin_section_height + sections * section_header_height + total * row_height + 60
    window_width = 440
    window_height = min(max(content_height, 220), 600)

    base = BaseDialog(title=title, width=window_width, height=window_height, position="center", border_color="#3B8ED0", track_dialog_state=False)
    if not base.is_valid():
        return

    header_frame = ctk.CTkFrame(base.main_frame, fg_color="transparent", height=36)
    header_frame.pack(fill="x", padx=12, pady=(12, 4))
    header_frame.pack_propagate(False)

    title_label = ctk.CTkLabel(
        header_frame,
        text=f"🧠  {title}",
        font=("Microsoft JhengHei", 12, "bold"),
        text_color="#3B8ED0",
        anchor="w",
    )
    title_label.pack(side="left", fill="y")

    count_label = ctk.CTkLabel(
        header_frame,
        text=f"📌 {len(manual_items)}  🕒 {len(auto_items)}",
        font=("Microsoft JhengHei", 11),
        text_color=("gray40", "gray55"),
        anchor="e",
    )
    count_label.pack(side="right", fill="y")

    if has_clipboard and on_memorize:
        pin_frame = ctk.CTkFrame(base.main_frame, fg_color=("#E8F4FD", "#1A2A3A"), corner_radius=8)
        pin_frame.pack(fill="x", padx=12, pady=(4, 4))

        clip_preview = clipboard_preview.replace("\n", " ").strip()
        if len(clip_preview) > 50:
            clip_preview = clip_preview[:50] + "…"

        clip_label = ctk.CTkLabel(
            pin_frame,
            text=f"📋 剪貼簿: {clip_preview}",
            font=("Microsoft JhengHei", 10),
            text_color=("gray30", "gray70"),
            anchor="w",
        )
        clip_label.pack(fill="x", padx=10, pady=(6, 2))

        input_row = ctk.CTkFrame(pin_frame, fg_color="transparent")
        input_row.pack(fill="x", padx=10, pady=(0, 6))

        comment_entry = ctk.CTkEntry(
            input_row,
            placeholder_text="加上註解 (可選)…",
            font=("Microsoft JhengHei", 10),
            height=28,
        )
        comment_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))

        def do_pin():
            comment_text = comment_entry.get().strip() or None
            on_memorize(comment_text)
            pin_btn.configure(text="✅ 已釘選", state="disabled", fg_color="#2e7d32")
            comment_entry.configure(state="disabled")
            new_count = len(manual_items) + 1
            count_label.configure(text=f"📌 {new_count}  🕒 {len(auto_items)}")

        pin_btn = ctk.CTkButton(
            input_row,
            text="📌 Pin",
            width=70,
            height=28,
            font=("Microsoft JhengHei", 10, "bold"),
            fg_color="#2e86c1",
            hover_color="#1a5276",
            command=do_pin,
        )
        pin_btn.pack(side="right")
        comment_entry.bind("<Return>", lambda e: do_pin())

    # Pack footer at bottom first so scroll_frame can expand into remaining space
    footer_frame = ctk.CTkFrame(base.main_frame, fg_color="transparent")
    footer_frame.pack(side="bottom", fill="x", padx=12, pady=(4, 10))

    def close(event=None):
        base.lifecycle.close()

    close_hint = ctk.CTkLabel(
        footer_frame,
        text="Esc to close",
        font=("Microsoft JhengHei", 10),
        text_color=("gray50", "gray60"),
        anchor="e",
    )
    close_hint.pack(side="right")

    scroll_frame = ctk.CTkScrollableFrame(
        base.main_frame,
        fg_color="transparent",
        scrollbar_button_color=("#c0c0c0", "#555555"),
        scrollbar_button_hover_color=("#a0a0a0", "#777777"),
    )
    scroll_frame.pack(fill="both", expand=True, padx=12, pady=(0, 5))

    def _format_time_ago(iso_str):
        try:
            ts = datetime.fromisoformat(iso_str)
            delta = datetime.now() - ts
            secs = int(delta.total_seconds())
            if secs < 60:
                return f"{secs}s ago"
            elif secs < 3600:
                return f"{secs // 60}m ago"
            else:
                return f"{secs // 3600}h ago"
        except Exception:
            return ""

    def _truncate(text, max_len=60):
        text = text.replace("\n", " ").strip()
        if len(text) > max_len:
            return text[:max_len] + "…"
        return text

    if total == 0:
        empty_label = ctk.CTkLabel(
            scroll_frame,
            text="目前沒有記憶內容。\n使用上方 📌 Pin 按鈕釘選剪貼簿內容，\n或短按 Alt+Shift+M 快速記住。",
            font=("Microsoft JhengHei", 12),
            text_color=("gray50", "gray60"),
            justify="center",
        )
        empty_label.pack(pady=20)

    if manual_items:
        pinned_header = ctk.CTkLabel(
            scroll_frame,
            text="📌 Pinned (Locked Memory)",
            font=("Microsoft JhengHei", 12, "bold"),
            text_color=("#B8860B", "#FFD700"),
            anchor="w",
        )
        pinned_header.pack(fill="x", padx=8, pady=(8, 2))

        sep = ctk.CTkFrame(scroll_frame, height=1, fg_color=("#DAA520", "#665500"))
        sep.pack(fill="x", padx=8, pady=(0, 4))

        for idx, mem in enumerate(manual_items):
            row = ctk.CTkFrame(scroll_frame, fg_color=("#F5F0E0", "#2A2A1E"), corner_radius=6)
            row.pack(fill="x", padx=8, pady=2)

            content_text = _truncate(mem.get("content", ""))
            comment = mem.get("comment")
            time_ago = _format_time_ago(mem.get("timestamp", ""))

            info_frame = ctk.CTkFrame(row, fg_color="transparent")
            info_frame.pack(side="left", fill="x", expand=True, padx=8, pady=4)

            content_label = ctk.CTkLabel(
                info_frame,
                text=content_text,
                font=("Microsoft JhengHei", 10),
                anchor="w",
            )
            content_label.pack(fill="x", anchor="w")

            meta_parts = []
            if comment:
                meta_parts.append(f"💬 {comment}")
            if time_ago:
                meta_parts.append(time_ago)
            meta_text = "  ·  ".join(meta_parts)

            if meta_text:
                meta_label = ctk.CTkLabel(
                    info_frame,
                    text=meta_text,
                    font=("Microsoft JhengHei", 9),
                    text_color=("gray50", "gray55"),
                    anchor="w",
                )
                meta_label.pack(fill="x", anchor="w")

            if on_unpin:
                def make_unpin(i, r):
                    def do_unpin():
                        on_unpin(i)
                        r.pack_forget()
                        remaining = len(manual_items) - 1
                        count_label.configure(text=f"📌 {remaining}  🕒 {len(auto_items)}")
                    return do_unpin

                unpin_btn = ctk.CTkButton(
                    row,
                    text="✕",
                    width=28,
                    height=28,
                    font=("Consolas", 12),
                    fg_color="transparent",
                    hover_color=("#E0D0B0", "#443A20"),
                    text_color=("gray40", "gray55"),
                    command=make_unpin(idx, row),
                )
                unpin_btn.pack(side="right", padx=4, pady=4)

    if auto_items:
        recent_header = ctk.CTkLabel(
            scroll_frame,
            text="🕒 Recent (Auto Memory)",
            font=("Microsoft JhengHei", 12, "bold"),
            text_color=("#444444", "#BBBBBB"),
            anchor="w",
        )
        recent_header.pack(fill="x", padx=8, pady=(10, 2))

        sep2 = ctk.CTkFrame(scroll_frame, height=1, fg_color=("#DDDDDD", "#444444"))
        sep2.pack(fill="x", padx=8, pady=(0, 4))

        from clipai import memory_manager as _mm
        ttl_min = _mm.get_auto_memory_ttl()

        for mem in auto_items:
            row = ctk.CTkFrame(scroll_frame, fg_color="transparent", corner_radius=6)
            row.pack(fill="x", padx=8, pady=2)

            content_text = _truncate(mem.get("content", ""))
            time_ago = _format_time_ago(mem.get("timestamp", ""))
            action_id = mem.get("action_id", "")

            info_frame = ctk.CTkFrame(row, fg_color="transparent")
            info_frame.pack(side="left", fill="x", expand=True, padx=8, pady=4)

            content_label = ctk.CTkLabel(
                info_frame,
                text=content_text,
                font=("Microsoft JhengHei", 10),
                text_color=("gray40", "gray55"),
                anchor="w",
            )
            content_label.pack(fill="x", anchor="w")

            meta_parts = []
            if action_id:
                meta_parts.append(f"🔧 {action_id}")
            if time_ago:
                meta_parts.append(time_ago)
            if ttl_min > 0:
                meta_parts.append(f"⏳ TTL {ttl_min}m")
            meta_text = "  ·  ".join(meta_parts)

            if meta_text:
                meta_label = ctk.CTkLabel(
                    info_frame,
                    text=meta_text,
                    font=("Microsoft JhengHei", 9),
                    text_color=("gray60", "gray65"),
                    anchor="w",
                )
                meta_label.pack(fill="x", anchor="w")

    if on_clear_all and total > 0:
        def do_clear():
            on_clear_all()
            close()

        clear_btn = ctk.CTkButton(
            footer_frame,
            text="🗑️ Clear All",
            width=90,
            height=28,
            font=("Microsoft JhengHei", 10),
            fg_color="transparent",
            border_width=1,
            text_color=("#CC3333", "#FF6666"),
            hover_color=("#FFE0E0", "#442222"),
            command=do_clear,
        )
        clear_btn.pack(side="left")

    base.lifecycle.setup_close_on_escape(close)
    base.lifecycle.setup_close_on_focus_out(delay_ms=150, callback=close)
    base.lifecycle.setup_force_focus(delay_ms=100)
    base.lifecycle.run_dialog(track_dialog_state=False)

def show_rhythm_check(reason: str = "general") -> Optional[str]:
    """
    Show a Goal Alignment Check dialog.
    """
    messages = {
        "high_tempo": "互動頻率較高。\n是否確認目前方向？",
        "topic_drift": "主題似乎有所轉移。\n是否確認目前目標？",
        "long_session": "探索已持續一段時間。\n是否確認目前目標？",
        "general": "是否確認目前目標？",
    }

    message = messages.get(reason, messages["general"])
    
    base = BaseDialog(
        title="ClipAI - Goal Check",
        width=380, height=140,
        position="center",
        border_color="#3B8ED0",
        track_dialog_state=False
    )
    if not base.is_valid():
        return None
    
    result = {"choice": None}

    header_frame = ctk.CTkFrame(base.main_frame, fg_color="transparent", height=36)
    header_frame.pack(fill="x", padx=12, pady=(8, 0))
    header_frame.pack_propagate(False)

    title_label = ctk.CTkLabel(
        header_frame,
        text="🎯  ClipAI - Goal Check",
        font=("Microsoft JhengHei", 12, "bold"),
        text_color="#3B8ED0",
        anchor="w",
    )
    title_label.pack(side="left", fill="y")

    msg_label = ctk.CTkLabel(
        base.main_frame,
        text=message,
        font=("Microsoft JhengHei", 11),
        justify="center",
    )
    msg_label.pack(pady=(8, 10))

    btn_frame = ctk.CTkFrame(base.main_frame, fg_color="transparent")
    btn_frame.pack(fill="x", padx=12, pady=(0, 10))

    def make_choice(choice):
        result["choice"] = choice
        base.lifecycle.close()

    def on_cancel(event=None):
        base.lifecycle.close()

    buttons_cfg = [
        ("繼續探索", "continue_current", "transparent", 1),
        ("回到原始目標", "return_to_goal", "#2e86c1", 0),
        ("重新定義目標", "redefine_goal", "transparent", 1),
    ]

    for text, choice_val, fg, border in buttons_cfg:
        btn = ctk.CTkButton(
            btn_frame,
            text=text,
            width=100,
            height=28,
            font=("Microsoft JhengHei", 10),
            fg_color=fg,
            border_width=border,
            text_color=("gray10", "#DCE4EE"),
            command=lambda c=choice_val: make_choice(c),
        )
        btn.pack(side="left", padx=4, expand=True)

    base.lifecycle.setup_close_on_escape(on_cancel)
    base.lifecycle.schedule(30000, on_cancel)
    base.lifecycle.setup_force_focus(delay_ms=100)
    base.lifecycle.run_dialog(track_dialog_state=False)
    return result["choice"]

if __name__ == "__main__":
    print(f"User entered: {get_user_input()}")



