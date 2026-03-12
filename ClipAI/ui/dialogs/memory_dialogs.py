from __future__ import annotations

from datetime import datetime

import customtkinter as ctk

from clipai.ui.base_dialog import BaseDialog


def show_memory_confirmation(content_preview: str, memory_count: int, max_count: int = 5, on_undo=None):
    """Show a small, auto-dismissing toast after a pin action."""
    base = BaseDialog(
        title="ClipAI Memory",
        width=340,
        height=80,
        position="cursor",
        border_color="#3B8ED0",
        track_dialog_state=False,
    )
    if not base.is_valid():
        return {"undone": False}

    result = {"undone": False}
    preview = content_preview.strip().replace("\n", " ")
    if len(preview) > 40:
        preview = preview[:40] + "..."

    top_frame = ctk.CTkFrame(base.main_frame, fg_color="transparent")
    top_frame.pack(fill="x", padx=12, pady=(8, 2))

    info_label = ctk.CTkLabel(
        top_frame,
        text=f"Pinned ({memory_count}/{max_count}): {preview}",
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
        info_label.configure(text="Pin undone")
        undo_btn.configure(state="disabled", text="Undone")
        base.lifecycle.schedule(800, base.lifecycle.close)

    def close_toast(event=None):
        base.lifecycle.close()

    undo_btn = ctk.CTkButton(
        bottom_frame,
        text="Undo",
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
        text="Auto closes in 3s",
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


def show_memory_viewer(memory_data, on_unpin=None, on_clear_all=None, on_memorize=None, clipboard_preview="", title="ClipAI Memory Context"):
    """Display pinned and recent memory items in a scrollable panel."""
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

    base = BaseDialog(
        title=title,
        width=window_width,
        height=window_height,
        position="center",
        border_color="#3B8ED0",
        track_dialog_state=False,
    )
    if not base.is_valid():
        return

    header_frame = ctk.CTkFrame(base.main_frame, fg_color="transparent", height=36)
    header_frame.pack(fill="x", padx=12, pady=(12, 4))
    header_frame.pack_propagate(False)

    title_label = ctk.CTkLabel(
        header_frame,
        text=f"Memory: {title}",
        font=("Microsoft JhengHei", 12, "bold"),
        text_color="#3B8ED0",
        anchor="w",
    )
    title_label.pack(side="left", fill="y")

    count_label = ctk.CTkLabel(
        header_frame,
        text=f"Pinned {len(manual_items)}  Recent {len(auto_items)}",
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
            clip_preview = clip_preview[:50] + "..."

        clip_label = ctk.CTkLabel(
            pin_frame,
            text=f"Clipboard: {clip_preview}",
            font=("Microsoft JhengHei", 10),
            text_color=("gray30", "gray70"),
            anchor="w",
        )
        clip_label.pack(fill="x", padx=10, pady=(6, 2))

        input_row = ctk.CTkFrame(pin_frame, fg_color="transparent")
        input_row.pack(fill="x", padx=10, pady=(0, 6))

        comment_entry = ctk.CTkEntry(
            input_row,
            placeholder_text="Optional note",
            font=("Microsoft JhengHei", 10),
            height=28,
        )
        comment_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))

        def do_pin():
            comment_text = comment_entry.get().strip() or None
            on_memorize(comment_text)
            pin_btn.configure(text="Pinned", state="disabled", fg_color="#2e7d32")
            comment_entry.configure(state="disabled")
            count_label.configure(text=f"Pinned {len(manual_items) + 1}  Recent {len(auto_items)}")

        pin_btn = ctk.CTkButton(
            input_row,
            text="Pin",
            width=70,
            height=28,
            font=("Microsoft JhengHei", 10, "bold"),
            fg_color="#2e86c1",
            hover_color="#1a5276",
            command=do_pin,
        )
        pin_btn.pack(side="right")
        comment_entry.bind("<Return>", lambda e: do_pin())

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
            if secs < 3600:
                return f"{secs // 60}m ago"
            return f"{secs // 3600}h ago"
        except Exception:
            return ""

    def _truncate(text, max_len=60):
        text = text.replace("\n", " ").strip()
        if len(text) > max_len:
            return text[:max_len] + "..."
        return text

    if total == 0:
        empty_label = ctk.CTkLabel(
            scroll_frame,
            text="No memory yet.\nUse Pin to keep important clipboard context.",
            font=("Microsoft JhengHei", 12),
            text_color=("gray50", "gray60"),
            justify="center",
        )
        empty_label.pack(pady=20)

    if manual_items:
        pinned_header = ctk.CTkLabel(
            scroll_frame,
            text="Pinned",
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

            info_frame = ctk.CTkFrame(row, fg_color="transparent")
            info_frame.pack(side="left", fill="x", expand=True, padx=8, pady=4)

            content_label = ctk.CTkLabel(
                info_frame,
                text=_truncate(mem.get("content", "")),
                font=("Microsoft JhengHei", 10),
                anchor="w",
            )
            content_label.pack(fill="x", anchor="w")

            meta_parts = []
            if mem.get("comment"):
                meta_parts.append(f"Note: {mem['comment']}")
            time_ago = _format_time_ago(mem.get("timestamp", ""))
            if time_ago:
                meta_parts.append(time_ago)
            if meta_parts:
                meta_label = ctk.CTkLabel(
                    info_frame,
                    text="  |  ".join(meta_parts),
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
                        count_label.configure(text=f"Pinned {max(len(manual_items) - 1, 0)}  Recent {len(auto_items)}")
                    return do_unpin

                unpin_btn = ctk.CTkButton(
                    row,
                    text="x",
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
            text="Recent",
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

            info_frame = ctk.CTkFrame(row, fg_color="transparent")
            info_frame.pack(side="left", fill="x", expand=True, padx=8, pady=4)

            content_label = ctk.CTkLabel(
                info_frame,
                text=_truncate(mem.get("content", "")),
                font=("Microsoft JhengHei", 10),
                text_color=("gray40", "gray55"),
                anchor="w",
            )
            content_label.pack(fill="x", anchor="w")

            meta_parts = []
            if mem.get("action_id"):
                meta_parts.append(f"Action: {mem['action_id']}")
            time_ago = _format_time_ago(mem.get("timestamp", ""))
            if time_ago:
                meta_parts.append(time_ago)
            if ttl_min > 0:
                meta_parts.append(f"TTL {ttl_min}m")
            if meta_parts:
                meta_label = ctk.CTkLabel(
                    info_frame,
                    text="  |  ".join(meta_parts),
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
            text="Clear All",
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
