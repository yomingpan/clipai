from __future__ import annotations

import customtkinter as ctk

from ClipAI.ui.base_dialog import BaseDialog


COLORS = {
    "idle": (0, 82, 184),
    "success": (0, 176, 79),
    "error": (232, 17, 35),
    "warning": (255, 215, 0),
}


def _rgb_hex(color: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*color)


STATE_COLORS = {name: _rgb_hex(rgb) for name, rgb in COLORS.items()}
DEFAULT_BORDER = STATE_COLORS["idle"]


MOCK_RESULT = """Summary
Appetizer is a small dish served before the main course.

Meaning
It prepares the appetite and sets the tone for the meal.

Context
Common in restaurants, formal dinners, and multi-course meals.

Example
We ordered a mushroom tart as an appetizer before the steak.

Synonyms
Starter, hors d'oeuvre, first course."""


class MockBaseDialogSurface:
    def __init__(self) -> None:
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        self.dialog = BaseDialog(
            title="ClipAI",
            width=620,
            height=430,
            position="center",
            border_color=DEFAULT_BORDER,
        )
        self.dialog.root.overrideredirect(True)
        self.dialog.root.configure(fg_color="#E9EDF3")
        try:
            self.dialog.root.attributes("-transparentcolor", "#E9EDF3")
        except Exception:
            pass
        self.pinned = False
        self.speaking = False
        self.follow_up_visible = False
        self._content_rendered = False
        self._drag_offset_x = 0
        self._drag_offset_y = 0
        self._build()
        self._show_loading_then_result()

    def _build(self) -> None:
        self.dialog.root.configure(fg_color="#E9EDF3")
        self.dialog.main_frame.configure(
            fg_color="#FFFFFF",
            corner_radius=26,
            border_width=3,
            border_color=DEFAULT_BORDER,
        )
        self.dialog.main_frame.grid_columnconfigure(0, weight=1)
        self.dialog.main_frame.grid_rowconfigure(3, weight=1)

        header = ctk.CTkFrame(self.dialog.main_frame, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=22, pady=(22, 8))
        header.grid_columnconfigure(0, weight=1)

        title_area = ctk.CTkFrame(header, fg_color="transparent")
        title_area.grid(row=0, column=0, sticky="w")

        title_label = ctk.CTkLabel(
            title_area,
            text="ClipAI - Explain Word",
            font=ctk.CTkFont(size=23, weight="bold"),
            text_color="#020617",
        )
        title_label.pack(anchor="w")

        self.pin_button = ctk.CTkButton(
            header,
            text="📌",
            width=34,
            height=34,
            corner_radius=17,
            fg_color="#DBEAFE",
            hover_color="#BFDBFE",
            text_color="#0F172A",
            font=ctk.CTkFont(size=16),
            command=self._pin_or_close,
        )
        self.pin_button.grid(row=0, column=1, sticky="ne")
        self._enable_drag(header, title_area, title_label)

        actions = ctk.CTkFrame(self.dialog.main_frame, fg_color="transparent")
        actions.grid(row=1, column=0, sticky="w", padx=22, pady=(0, 10))
        self.speaker_button = self._slot_button(actions, "🔊 Speak", self._toggle_speaker, width=88)
        self.copy_button = self._slot_button(actions, "⧉ Copy", self._copy_visible_text, width=78)
        self.follow_button = self._slot_button(actions, "✎ Follow-up", self._toggle_follow_up, width=112)

        clipboard_label = ctk.CTkLabel(
            self.dialog.main_frame,
            text='Clipboard: "Appetizer is a small dish served before the main course..."',
            anchor="w",
            justify="left",
            font=ctk.CTkFont(size=13),
            text_color="#64748B",
            wraplength=550,
        )
        clipboard_label.grid(row=2, column=0, sticky="ew", padx=22, pady=(0, 12))

        self.content_card = ctk.CTkScrollableFrame(
            self.dialog.main_frame,
            fg_color="#F8FAFC",
            corner_radius=18,
            border_width=0,
        )
        self.content_card.grid(row=3, column=0, sticky="nsew", padx=22, pady=(0, 14))
        self.content_card.grid_columnconfigure(0, weight=1)

        self.loading_label = ctk.CTkLabel(
            self.content_card,
            text="Loading result...",
            anchor="w",
            justify="left",
            font=ctk.CTkFont(size=15),
            text_color="#334155",
        )
        self.loading_label.grid(row=0, column=0, sticky="w", padx=18, pady=18)

        self.follow_row = ctk.CTkFrame(self.dialog.main_frame, fg_color="transparent")
        self.follow_row.grid_columnconfigure(0, weight=1)
        self.follow_entry = ctk.CTkEntry(
            self.follow_row,
            height=42,
            corner_radius=12,
            border_width=1,
            border_color="#CBD5E1",
            fg_color="#FFFFFF",
            text_color="#020617",
            font=ctk.CTkFont(size=14),
        )
        self.follow_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.follow_entry.insert(0, "5 more examples")
        ctk.CTkButton(
            self.follow_row,
            text="Send",
            width=70,
            height=42,
            corner_radius=12,
            fg_color="#3B82F6",
            hover_color="#2563EB",
            font=ctk.CTkFont(size=14),
            command=self._fake_send,
        ).grid(row=0, column=1, sticky="e")

    def _slot_button(
        self,
        parent: ctk.CTkFrame,
        text: str,
        command,
        *,
        text_color: str = "#020617",
        width: int = 110,
    ) -> ctk.CTkButton:
        button = ctk.CTkButton(
            parent,
            text=text,
            width=width,
            height=32,
            corner_radius=10,
            fg_color="#EEF2F7",
            hover_color="#E3E8EF",
            text_color=text_color,
            font=ctk.CTkFont(size=13),
            command=command,
        )
        button.pack(side="left", padx=(0, 8))
        return button

    def _enable_drag(self, *widgets: ctk.CTkBaseClass) -> None:
        for widget in widgets:
            widget.bind("<ButtonPress-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._drag_window)

    def _start_drag(self, event) -> None:
        self._drag_offset_x = event.x_root - self.dialog.root.winfo_x()
        self._drag_offset_y = event.y_root - self.dialog.root.winfo_y()

    def _drag_window(self, event) -> None:
        x = event.x_root - self._drag_offset_x
        y = event.y_root - self._drag_offset_y
        self.dialog.root.geometry(f"+{x}+{y}")

    def _show_loading_then_result(self) -> None:
        self.dialog.lifecycle.schedule(700, self._show_result)

    def _show_result(self) -> None:
        self.loading_label.destroy()
        sections = [
            ("Summary", "Appetizer is a small dish served before the main course."),
            ("Meaning", "It prepares the appetite and sets the tone for the meal."),
            ("Context", "Common in restaurants, formal dinners, and multi-course meals."),
            ("Example", "We ordered a mushroom tart as an appetizer before the steak."),
            ("Synonyms", "Starter, hors d'oeuvre, first course."),
        ]
        for row, (heading, body) in enumerate(sections):
            top_pad = 26 if row == 0 else 22
            ctk.CTkLabel(
                self.content_card,
                text=heading,
                anchor="w",
                justify="left",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color="#0F172A",
            ).grid(row=row * 2, column=0, sticky="w", padx=18, pady=(top_pad, 5))
            ctk.CTkLabel(
                self.content_card,
                text=body,
                anchor="w",
                justify="left",
                wraplength=530,
                font=ctk.CTkFont(size=15),
                text_color="#020617",
            ).grid(row=row * 2 + 1, column=0, sticky="w", padx=18, pady=(0, 1))

        self._content_rendered = True
        self._flash_state("success")

    def _reset_status(self) -> None:
        self.dialog.main_frame.configure(border_color=DEFAULT_BORDER)

    def _flash_state(self, state: str) -> None:
        duration_ms = 1000 if state == "success" else 3000
        self.dialog.main_frame.configure(border_color=STATE_COLORS[state])
        self.dialog.lifecycle.schedule(duration_ms, self._reset_status)

    def _toggle_speaker(self) -> None:
        self.speaking = not self.speaking
        self.speaker_button.configure(
            text="■ Stop" if self.speaking else "🔊 Speak",
            text_color="#DC2626" if self.speaking else "#020617",
        )

    def _copy_visible_text(self) -> None:
        if self._content_rendered:
            self._flash_state("success")
        else:
            self._flash_state("warning")

    def _toggle_follow_up(self) -> None:
        self.follow_up_visible = not self.follow_up_visible
        if self.follow_up_visible:
            self.follow_row.grid(row=4, column=0, sticky="ew", padx=22, pady=(0, 20))
            self.dialog.lifecycle.focus(self.follow_entry)
        else:
            self.follow_row.grid_forget()

    def _pin_or_close(self) -> None:
        if self.pinned:
            self.dialog.lifecycle.close()
            return
        self.pinned = True
        self.pin_button.configure(
            text="×",
            fg_color="#FEE2E2",
            hover_color="#FECACA",
            text_color="#B91C1C",
            font=ctk.CTkFont(size=20, weight="bold"),
        )

    def _fake_send(self) -> None:
        prompt = self.follow_entry.get().strip().lower()
        if not prompt:
            self._flash_state("warning")
        elif prompt == "error":
            self._flash_state("error")
        else:
            self._flash_state("success")

    def _fake_stop(self) -> None:
        self.speaking = False
        self.speaker_button.configure(text="🔊 Speak", text_color="#020617")

    def run(self) -> None:
        self.dialog.run_dialog()


def main() -> None:
    MockBaseDialogSurface().run()


if __name__ == "__main__":
    main()
