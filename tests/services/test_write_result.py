import pytest

from ClipAI.core.errors import CancelledError
from ClipAI.core.models import ForegroundTarget
from ClipAI.core.state import CancellationToken
from ClipAI.services.write_result import WriteResultSink


class Targets:
    def __init__(self, target):
        self.target = target

    def current(self):
        return self.target


class Outputs:
    can_paste = True

    def __init__(self):
        self.pasted = []

    def paste(self, text):
        self.pasted.append(text)


def test_write_requires_the_original_foreground_target():
    outputs = Outputs()
    sink = WriteResultSink(Targets(ForegroundTarget(2)), outputs)
    with pytest.raises(CancelledError, match="target window changed"):
        sink.write_result("result", ForegroundTarget(1), "workflow", CancellationToken())
    assert outputs.pasted == []


def test_write_pastes_when_target_is_unchanged():
    outputs = Outputs()
    sink = WriteResultSink(Targets(ForegroundTarget(1)), outputs)
    sink.write_result("result", ForegroundTarget(1), "workflow", CancellationToken())
    assert outputs.pasted == ["result"]
