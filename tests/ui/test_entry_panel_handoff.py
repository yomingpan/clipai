from __future__ import annotations

from ClipAI.core.models import PopupBounds
from ClipAI.ui.entry_panel_handoff import EntryPanelPopupHandoff


class Panel:
    def __init__(self, events: list[str]) -> None:
        self._events = events
        self._panel_id = "panel-1"
        self._open = True
        self.bounds = PopupBounds(120, 80, 400, 320)

    def presents(self, panel_id: str) -> bool:
        return self._open and panel_id == self._panel_id

    def current_bounds(self) -> PopupBounds:
        self._events.append("panel:bounds")
        return self.bounds

    def hide(self) -> None:
        self._events.append("panel:hidden")

    def reveal(self) -> None:
        self._events.append("panel:revealed")

    def close(self) -> None:
        self._events.append("panel:closed")
        self._open = False


class Popup:
    def __init__(self, events: list[str], *show_outcomes: bool) -> None:
        self._events = events
        self._show_outcomes = iter(show_outcomes or (True,))

    def show(self) -> bool:
        self._events.append("popup:shown")
        return next(self._show_outcomes)


def test_begin_rejects_a_stale_panel_identity() -> None:
    events: list[str] = []
    handoff = EntryPanelPopupHandoff(Panel(events))

    assert handoff.begin("stale-panel", "workflow-1") is False
    assert handoff.prepare("workflow-1", popup_exists=False) is None
    assert events == []


def test_prepare_is_workflow_scoped_and_keeps_the_panel_visible() -> None:
    events: list[str] = []
    panel = Panel(events)
    handoff = EntryPanelPopupHandoff(panel)
    assert handoff.begin("panel-1", "workflow-1") is True

    assert handoff.prepare("other-workflow", popup_exists=False) is None
    preparation = handoff.prepare("workflow-1", popup_exists=False)

    assert preparation is not None
    assert preparation.bounds == PopupBounds(120, 80, 400, 320)
    assert preparation.create_withdrawn is True
    assert events == ["panel:bounds"]


def test_new_popup_commits_hide_show_close_in_order() -> None:
    events: list[str] = []
    panel = Panel(events)
    handoff = EntryPanelPopupHandoff(panel)
    assert handoff.begin("panel-1", "workflow-1") is True
    assert handoff.prepare("workflow-1", popup_exists=False) is not None
    events.clear()

    completion = handoff.complete("workflow-1", Popup(events, True))

    assert completion.committed is True
    assert completion.popup_revealed is True
    assert events == ["panel:hidden", "popup:shown", "panel:closed"]


def test_failed_popup_reveal_rolls_back_the_same_panel_and_remains_retryable() -> None:
    events: list[str] = []
    panel = Panel(events)
    popup = Popup(events, False, True)
    handoff = EntryPanelPopupHandoff(panel)
    assert handoff.begin("panel-1", "workflow-1") is True
    preparation = handoff.prepare("workflow-1", popup_exists=False)
    assert preparation is not None
    events.clear()

    first = handoff.complete("workflow-1", popup)
    second_preparation = handoff.prepare("workflow-1", popup_exists=True)
    second = handoff.complete("workflow-1", popup)

    assert first.committed is False
    assert second_preparation == preparation
    assert second.committed is True
    assert second.popup_revealed is True
    assert events == [
        "panel:hidden",
        "popup:shown",
        "panel:revealed",
        "panel:hidden",
        "popup:shown",
        "panel:closed",
    ]


def test_reused_popup_keeps_its_geometry_and_only_closes_the_panel() -> None:
    events: list[str] = []
    panel = Panel(events)
    popup = Popup(events)
    handoff = EntryPanelPopupHandoff(panel)
    assert handoff.begin("panel-1", "workflow-1") is True

    preparation = handoff.prepare("workflow-1", popup_exists=True)
    completion = handoff.complete("workflow-1", popup)

    assert preparation is not None
    assert preparation.bounds is None
    assert preparation.create_withdrawn is False
    assert completion.committed is True
    assert completion.popup_revealed is False
    assert events == ["panel:closed"]


def test_completion_before_preparation_is_ignored() -> None:
    events: list[str] = []
    handoff = EntryPanelPopupHandoff(Panel(events))
    assert handoff.begin("panel-1", "workflow-1") is True

    completion = handoff.complete("workflow-1", Popup(events))

    assert completion.committed is False
    assert completion.popup_revealed is False
    assert events == []
