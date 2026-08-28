from __future__ import annotations

import customtkinter as ctk

from ClipAI.core.models import ActionFeedbackContract, FeedbackReason
from ClipAI.ui.base_dialog import BaseDialog, BaseResultSurface


COLORS = {
    "idle": (31, 106, 165),
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
            width=400,
            height=420,
            position="center",
            state_colors=COLORS,
            background_color="#E9EDF3",
            surface_color="#2B2B2B",
            frameless=True,
            transparent_background=True,
            surface_inset=8,
            corner_radius=18,
        )
        self.surface = BaseResultSurface(self.dialog)
        self.feedback_contract = ActionFeedbackContract(
            "縮短內容、移除重複，並維持原有結構",
            "保留原本的立場、事實、語氣與語言",
            (
                FeedbackReason("meaning_or_fact_lost", "核心意思或重要事實少了"),
                FeedbackReason("key_detail_missing", "縮得太多，關鍵細節不夠"),
                FeedbackReason("other", "其他"),
            ),
        )
        self.speaking = False
        self.content_rendered = False
        self._build()
        self.dialog.lifecycle.schedule(700, self._show_result)
        self.dialog.lifecycle.schedule(1100, self.surface.show_action_guidance_hint)

    def _build(self) -> None:
        self.surface.set_title("ClipAI - 改成口語可說出口版本")
        self.surface.set_source_preview("🔍 Analyzing: 這樣可以，還可以這樣。像這樣跟他講話。然後我修好的...")
        self.surface.set_model("gpt-5.4")
        self.surface.configure_action_contract(self.feedback_contract, "selection")
        self.surface.configure_standard_actions(
            on_speak=self._toggle_speaker,
            on_copy=self._copy_visible_text,
            on_follow_up=self._toggle_follow_up,
        )
        self.surface.follow_entry.insert(0, "5 more examples")
        self.surface.follow_send_button.configure(command=self._fake_send)
        self.surface.set_loading()

    def _show_result(self) -> None:
        self.surface.set_content_chunks(
            [
                (
                    "可以這樣跟他說：我把那個會一直跳來跳去的問題修好了，"
                    "現在你按住拖動也不會亂閃。之前會這樣，主要是因為你按很多螢幕時，"
                    "每個螢幕的顯示大小不太一樣，所以系統會搞混；如果只用一個螢幕，"
                    "通常就沒事。還有，你處理完之後按一下 Ctrl+P，就可以把內容整理好，"
                    "接著你再繼續講，它也會記得前面在說什麼；如果中間停一下，"
                    "它也會自己想一下再接上。"
                    "可以這樣跟他說：我把那個會一直跳來跳去的問題修好了，"
                    "現在你按住拖動也不會亂閃。之前會這樣，主要是因為你按很多螢幕時，"
                    "每個螢幕的顯示大小不太一樣，所以系統會搞混；如果只用一個螢幕，"
                    "通常就沒事。還有，你處理完之後按一下 Ctrl+P，就可以把內容整理好，"
                    "接著你再繼續講，它也會記得前面在說什麼；如果中間停一下，"
                    "它也會自己想一下再接上。",
                    "body",
                )
            ]
        )
        self.content_rendered = True
        self.surface.configure_feedback(self.feedback_contract, "idle", "", self._record_feedback)
        self.dialog.flash("success")

    def _record_feedback(self, outcome, reason, note, save_case) -> None:
        del outcome, reason, note, save_case
        self.surface.configure_feedback(self.feedback_contract, "succeeded", "已記錄回饋", self._record_feedback)

    def _toggle_speaker(self) -> None:
        self.speaking = not self.speaking
        self.surface.set_speaker_active(self.speaking)

    def _copy_visible_text(self) -> None:
        self.dialog.flash("success" if self.content_rendered else "warning")

    def _toggle_follow_up(self) -> None:
        if self.surface.follow_up_visible:
            self.surface.hide_follow_up()
        else:
            self.surface.show_follow_up()
        self.surface.set_follow_up_active(self.surface.follow_up_visible)

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
