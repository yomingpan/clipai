from __future__ import annotations

import customtkinter as ctk

from ClipAI.ui.base_dialog import BaseDialog, BaseResultSurface


COLORS = {
    "idle": (0, 82, 184),
    "success": (0, 176, 79),
    "error": (232, 17, 35),
    "warning": (255, 215, 0),
}


class MockBaseDialogSurface:
    def __init__(self) -> None:
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        self.dialog = BaseDialog(
            title="ClipAI",
            width=520,
            height=350,
            position="center",
            state_colors=COLORS,
            frameless=True,
            transparent_background=True,
            surface_inset=8,
            corner_radius=18,
        )
        self.surface = BaseResultSurface(self.dialog)
        self.speaking = False
        self.content_rendered = False
        self._build()
        self.dialog.lifecycle.schedule(700, self._show_result)

    def _build(self) -> None:
        self.surface.set_title("ClipAI - Explain Word")
        self.surface.set_source_preview('Clipboard: "Appetizer is a small dish served before the main course..."')
        self.speaker_button = self.surface.add_action_slot("speaker", "🔊 Speak", self._toggle_speaker, width=56)
        self.surface.add_action_slot("copy", "⧉ Copy", self._copy_visible_text, width=48)
        self.surface.add_action_slot("follow_up", "✎ Follow", self._toggle_follow_up, width=60)
        self.surface.follow_entry.insert(0, "5 more examples")
        self.surface.follow_send_button.configure(command=self._fake_send)
        self.surface.set_loading()

    def _show_result(self) -> None:
        self.surface.set_sections(
            [
                ("Summary", "Appetizer is a small dish served before the main course."),
                ("Meaning", "It prepares the appetite and sets the tone for the meal."),
                ("Context", "Common in restaurants, formal dinners, and multi-course meals."),
                ("Example", "We ordered a mushroom tart as an appetizer before the steak."),
                ("Synonyms", "Starter, hors d'oeuvre, first course."),
            ]
        )
        self.content_rendered = True
        self.dialog.flash("success")

    def _toggle_speaker(self) -> None:
        self.speaking = not self.speaking
        self.speaker_button.configure(
            text="■ Stop" if self.speaking else "🔊 Speak",
            text_color="#DC2626" if self.speaking else "#020617",
        )

    def _copy_visible_text(self) -> None:
        self.dialog.flash("success" if self.content_rendered else "warning")

    def _toggle_follow_up(self) -> None:
        if self.surface.follow_up_visible:
            self.surface.hide_follow_up()
        else:
            self.surface.show_follow_up()

    def _fake_send(self) -> None:
        prompt = self.surface.follow_entry.get().strip().lower()
        if not prompt:
            self.dialog.flash("warning")
        elif prompt == "error":
            self.dialog.flash("error")
        else:
            self.dialog.flash("success")

    def run(self) -> None:
        self.dialog.run_dialog()


def main() -> None:
    MockBaseDialogSurface().run()


if __name__ == "__main__":
    main()
