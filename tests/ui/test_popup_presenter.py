from __future__ import annotations

from pathlib import Path

from clipai.services.popup_session import PopupSession
from clipai.ui.popup_presenter import PopupPresenter


def test_speak_phase_to_ui_state_is_phase_aware() -> None:
    assert PopupPresenter._speak_phase_to_ui_state("start", True) is True
    assert PopupPresenter._speak_phase_to_ui_state("stop", False) is False
    assert PopupPresenter._speak_phase_to_ui_state("end", False) is False
    assert PopupPresenter._speak_phase_to_ui_state("error", False) is False
    assert PopupPresenter._speak_phase_to_ui_state("", True) is True
    assert PopupPresenter._speak_phase_to_ui_state("", False) is None


def test_popup_presenter_uses_ctrl_slash_not_ctrl_m() -> None:
    content = Path("clipai/ui/popup_presenter.py").read_text(encoding="utf-8")
    assert "<Control-slash>" in content
    assert "<Control-question>" in content
    assert "<Control-m>" not in content
    assert "<Control-Alt-Q>" in content
    assert "<Alt-Shift-Q>" not in content


def test_popup_presenter_has_auto_close_grace_period() -> None:
    content = Path("clipai/ui/popup_presenter.py").read_text(encoding="utf-8")
    assert "CLOSE_GRACE_SEC" in content
    assert "_suppress_auto_close" in content


def test_popup_presenter_focus_close_is_not_blocked_by_tts() -> None:
    content = Path("clipai/ui/popup_presenter.py").read_text(encoding="utf-8")
    assert "if self._tts_service is not None and self._tts_service.is_speaking():\n                return" not in content
    assert "if self._tts_service is not None and self._tts_service.is_speaking():\n                self._tts_service.stop()" not in content


def test_popup_presenter_clears_follow_up_entry_on_reuse() -> None:
    content = Path("clipai/ui/popup_presenter.py").read_text(encoding="utf-8")
    assert "_clear_follow_up_entry_on_ui" in content
    assert "self._clear_follow_up_entry_on_ui()" in content


def test_popup_presenter_hides_follow_up_after_submit() -> None:
    content = Path("clipai/ui/popup_presenter.py").read_text(encoding="utf-8")
    assert 'self._follow_frame.pack_forget()' in content
    assert 'self._follow_visible = False' in content


def test_popup_presenter_sets_readability_selection_colors_and_font_sizes() -> None:
    content = Path("clipai/ui/popup_presenter.py").read_text(encoding="utf-8")
    assert 'SELECTION_BG_COLOR = "#2A4E7A"' in content
    assert 'SELECTION_FG_COLOR = "#F7FAFF"' in content
    assert 'font=("Microsoft JhengHei", 11)' in content
    assert 'font=("Microsoft JhengHei", 10)' in content
    assert 'font=("Consolas", 10)' in content
    assert 'foreground=code_fg' in content
    assert 'background=code_bg' in content


def test_popup_presenter_uses_neutral_border_color() -> None:
    content = Path("clipai/ui/popup_presenter.py").read_text(encoding="utf-8")
    assert 'POPUP_BORDER_COLOR = "#3A4454"' in content
    assert 'POPUP_TITLE_COLOR = "#4F89D9"' in content


def test_popup_presenter_has_theme_aware_inline_code_palette() -> None:
    content = Path("clipai/ui/popup_presenter.py").read_text(encoding="utf-8")
    assert "def _code_tag_palette" in content
    assert 'return "#2C3442", "#F7FAFF"' in content
    assert 'return "#EEF3F8", "#1F2937"' in content


def test_popup_presenter_uses_shared_selection_or_full_policy_for_actions() -> None:
    content = Path("clipai/ui/popup_presenter.py").read_text(encoding="utf-8")
    assert "def _selected_output_or_full" in content
    assert "payload = self._selected_output_or_full(self._text_widget, session)" in content
    assert "content = self._selected_output_or_full(self._text_widget, session)" in content


def test_popup_presenter_clears_text_selection_when_hiding_follow_up() -> None:
    content = Path("clipai/ui/popup_presenter.py").read_text(encoding="utf-8")
    assert "def _clear_text_selection_on_ui" in content
    assert 'text_widget.tag_remove("sel", "1.0", "end")' in content
    assert "self._clear_text_selection_on_ui(self._text_widget)" in content


def test_popup_presenter_input_preview_and_result_respect_loading_flags() -> None:
    session = PopupSession(
        action_id="summarize_next_steps",
        action_name="Summary",
        original_input="",
        latest_result="",
        input_loading=True,
        result_loading=True,
    )

    assert PopupPresenter._input_preview_for_session(session) == "Analysis: Connecting..."
    assert PopupPresenter._result_text_for_session(session) == "Connecting..."

    session.mark_input_ready("hello world")
    session.mark_result_ready("final answer")

    assert PopupPresenter._input_preview_for_session(session) == "Analysis: hello world"
    assert PopupPresenter._result_text_for_session(session) == "final answer"


def test_popup_presenter_refresh_session_repaints_input_preview_from_session_state() -> None:
    class _FakeLabel:
        def __init__(self) -> None:
            self.text = None

        def configure(self, **kwargs) -> None:
            self.text = kwargs.get("text")

    presenter = PopupPresenter()
    presenter._input_label = _FakeLabel()
    presenter._text_widget = None
    presenter._follow_entry = None
    presenter._follow_hint_label = None

    first = PopupSession(
        action_id="first",
        action_name="First",
        original_input="",
        latest_result="",
        input_loading=True,
        result_loading=True,
    )
    first.mark_input_ready("first input")
    presenter._active_session = first
    presenter._refresh_session_on_ui(first.session_id)
    assert presenter._input_label.text == "Analysis: first input"

    second = PopupSession(
        action_id="second",
        action_name="Second",
        original_input="second input",
        latest_result="done",
        input_loading=False,
        result_loading=False,
    )
    presenter._active_session = second
    presenter._refresh_session_on_ui(second.session_id)
    assert presenter._input_label.text == "Analysis: second input"
