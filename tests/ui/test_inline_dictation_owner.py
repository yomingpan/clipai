from __future__ import annotations

import pytest

from ClipAI.core.models import PasteOutcome
from ClipAI.core.voice import InlineDictationView
from ClipAI.ui.inline_dictation_owner import InlineDictationInterfaceOwner


def setup_owner(monkeypatch, native=None):
    import ClipAI.ui.inline_dictation_owner as module
    windows, jobs, commands = [], [], []
    class Root:
        def after(self, delay, callback): jobs.append((delay, callback)); return str(len(jobs))
        def after_cancel(self, job): pass
    class Window:
        def __init__(self, _root, **kwargs):
            self.interaction_id = kwargs["interaction_id"]
            self.views, self.closed, self.callbacks = [], [], kwargs
            windows.append(self)
        def show(self): pass
        def close(self): self.closed.append(True)
        def present(self, view): self.views.append(view)
    monkeypatch.setattr(module, "InlinePill", Window)
    return InlineDictationInterfaceOwner(Root(), commands.append, native_window_surface=native), windows, jobs, commands


def test_owner_ignores_late_result_and_close_for_replaced_interaction(monkeypatch):
    owner, windows, _, _ = setup_owner(monkeypatch)
    owner.open_inline_dictation("old")
    owner.open_inline_dictation("new")
    owner.present_inline_dictation(InlineDictationView("old", "recovery", text="old"))
    current = InlineDictationView("new", "recovery", text="new")
    owner.present_inline_dictation(current)
    owner.close_inline_dictation(interaction_id="old")
    assert windows[0].closed == [True]
    assert windows[1].views == [current]
    assert windows[1].closed == []


@pytest.mark.parametrize("state, delay", [("dispatched_unconfirmed", 600), ("cancelled", 1200)])
def test_terminal_dwell_schedules_one_identity_scoped_dismiss(monkeypatch, state, delay):
    owner, windows, jobs, commands = setup_owner(monkeypatch)
    owner.open_inline_dictation("i")
    view = InlineDictationView("i", "settled", paste_outcome=PasteOutcome(state, "not_dispatched", "not_required"))
    owner.present_inline_dictation(view)
    owner.present_inline_dictation(view)
    assert len(jobs) == 1 and jobs[0][0] == delay
    jobs[0][1]()
    from ClipAI.core.commands import DismissInlineDictationTerminal
    assert commands == [DismissInlineDictationTerminal("i")]
    owner.open_inline_dictation("new")
    jobs[0][1]()
    assert len(commands) == 1


def test_closed_message_flashes_for_three_seconds_without_closing_replacement(monkeypatch):
    owner, windows, jobs, _ = setup_owner(monkeypatch)
    owner.open_inline_dictation("old")
    view = InlineDictationView("old", "closed", message="microphone unavailable")
    owner.present_inline_dictation(view)
    assert windows[0].views == [view]
    assert windows[0].closed == []
    assert jobs[0][0] == 3000
    owner.open_inline_dictation("new")
    jobs[0][1]()
    assert windows[1].closed == []


def test_callbacks_keep_original_interaction_and_native_port_when_replaced(monkeypatch):
    from ClipAI.core.commands import CancelInlineDictation, ConfirmInlineDictation, CopyInlineDictation
    native = object()
    owner, windows, _, commands = setup_owner(monkeypatch, native)
    owner.open_inline_dictation("old", "choice")
    callbacks = windows[0].callbacks
    assert callbacks["native_window_surface"] is native
    owner.open_inline_dictation("new", "minimal")
    callbacks["on_cancel"]()
    callbacks["on_confirm"](True)
    callbacks["on_copy"]()
    assert commands == [CancelInlineDictation("old"), ConfirmInlineDictation("old", True), CopyInlineDictation("old")]
    assert windows[1].closed == []
