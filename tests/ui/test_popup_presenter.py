from __future__ import annotations

from pathlib import Path

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
