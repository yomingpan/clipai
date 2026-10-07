from __future__ import annotations

from ClipAI.core.models import PasteOutcome
from ClipAI.ui.inline_dictation_owner import InlineDictationInterfaceOwner


def test_owner_ignores_late_result_and_close_for_replaced_interaction(monkeypatch) -> None:
    import ClipAI.ui.inline_dictation_owner as module

    windows = []

    class Window:
        def __init__(self, _root, **kwargs) -> None:
            self.interaction_id = kwargs["interaction_id"]
            self.results = []
            self.closed = []
            windows.append(self)

        def show(self) -> None: pass
        def close(self, **kwargs) -> None: self.closed.append(kwargs)
        def show_paste_outcome(self, outcome, text) -> None: self.results.append((outcome, text))

    monkeypatch.setattr(module, "InlineDictationWindow", Window)
    owner = InlineDictationInterfaceOwner(object(), lambda _command: None)
    owner.open_inline_dictation("old")
    owner.open_inline_dictation("new", placement="bottom_center")
    outcome = PasteOutcome("failed", "not_dispatched", "not_required")
    owner.present_inline_paste_outcome("old", outcome, "old")
    owner.present_inline_paste_outcome("new", outcome, "new")
    owner.close_inline_dictation(interaction_id="old")
    assert windows[0].closed == [{}]
    assert windows[1].results == [(outcome, "new")]
    assert windows[1].closed == []
