from __future__ import annotations

from collections import OrderedDict

import customtkinter as ctk

from clipai.platform.hotkey import expand_hotkeys
from clipai.ui.base_dialog import BaseDialog


BEHAVIOR_LABELS = {
    "paste": "[Paste]",
    "popup": "[Popup]",
    "speak": "[Speak]",
    "memory": "[Memory]",
}


def _behavior_label(action: dict) -> str:
    output_cfg = action.get("output", {})
    action_id = str(action.get("id", ""))
    if action_id == "tts_read_selection":
        return BEHAVIOR_LABELS["speak"]
    if action_id in ("memorize", "reset_memory"):
        return BEHAVIOR_LABELS["memory"]
    if output_cfg.get("show_popup", False) or action.get("output_mode") == "popup":
        return BEHAVIOR_LABELS["popup"]
    return BEHAVIOR_LABELS["paste"]


def _display_name(action: dict) -> str:
    raw_name = str(action.get("name") or "").strip()
    if raw_name and "?" not in raw_name:
        return raw_name
    action_id = str(action.get("id") or "Unnamed Action")
    return action_id.replace("_", " ").title()


def _format_hotkeys(hotkey: str, modifier_mode: str) -> str:
    variants = []
    for item in expand_hotkeys(hotkey, modifier_mode=modifier_mode):
        text = item.replace("ctrl+", "Ctrl+").replace("alt+", "Alt+").replace("shift+", "Shift+")
        variants.append(text)
    return " / ".join(dict.fromkeys(variants))


def show_hotkey_guide(actions_list, title="ClipAI Hotkey Guide", modifier_mode: str = "ctrl_alt"):
    """Display a grouped hotkey reference panel."""
    groups: OrderedDict = OrderedDict()
    for action in actions_list:
        hotkey = action.get("hotkey")
        if not hotkey:
            continue
        group_name = action.get("group", "Other")
        groups.setdefault(group_name, []).append(action)

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
        text="[AI]  " + title,
        font=("Microsoft JhengHei", 12, "bold"),
        text_color="#3B8ED0",
        anchor="w",
    )
    title_label.pack(side="left", fill="y")

    footer_frame = ctk.CTkFrame(base.main_frame, fg_color="transparent")
    footer_frame.pack(side="bottom", fill="x", padx=12, pady=(4, 10))

    legend = ctk.CTkLabel(
        footer_frame,
        text="  ".join(BEHAVIOR_LABELS.values()) + f"    Mode: {modifier_mode}",
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

        for action in items:
            row = ctk.CTkFrame(scroll_frame, fg_color="transparent")
            row.pack(fill="x", padx=8, pady=1)

            display_name = f"{_behavior_label(action)}  {_display_name(action)}"
            name_label = ctk.CTkLabel(
                row,
                text=display_name,
                font=("Microsoft JhengHei", 11),
                anchor="w",
            )
            name_label.pack(side="left", fill="x", expand=True)

            hk_text = _format_hotkeys(str(action["hotkey"]), modifier_mode)
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
