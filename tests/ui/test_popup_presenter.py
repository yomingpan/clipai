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


def test_popup_presenter_clears_follow_up_entry_on_reuse() -> None:
    content = Path("clipai/ui/popup_presenter.py").read_text(encoding="utf-8")
    assert "_clear_follow_up_entry_on_ui" in content
    assert "self._clear_follow_up_entry_on_ui()" in content


def test_popup_presenter_hides_follow_up_after_submit() -> None:
    content = Path("clipai/ui/popup_presenter.py").read_text(encoding="utf-8")
    assert 'self._follow_frame.pack_forget()' in content
    assert 'self._follow_visible = False' in content
