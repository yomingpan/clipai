import pytest

from scripts.popup_first_frame_benchmark import _await_presented_frame


class _Window:
    def __init__(self, viewable: bool) -> None:
        self.viewable = viewable
        self.idle_tasks_updated = False

    def update_idletasks(self) -> None:
        self.idle_tasks_updated = True

    def winfo_viewable(self) -> bool:
        return self.viewable


def test_presented_frame_processes_events_and_waits_for_compositor():
    window = _Window(True)
    flushed = []

    _await_presented_frame(window, flush=lambda: flushed.append(True))

    assert window.idle_tasks_updated
    assert flushed == [True]


def test_presented_frame_rejects_a_nonvisible_window_before_compositor_claim():
    window = _Window(False)
    flushed = []

    with pytest.raises(RuntimeError, match="viewable"):
        _await_presented_frame(window, flush=lambda: flushed.append(True))

    assert flushed == []
