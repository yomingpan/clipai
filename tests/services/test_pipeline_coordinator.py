from __future__ import annotations

from clipai.core.event_bus import EventBus
from clipai.services.pipeline_coordinator import PipelineCoordinator


def test_pipeline_coordinator_cancels_previous_session() -> None:
    bus = EventBus()
    pc = PipelineCoordinator(bus)

    s1 = pc.start_session("s1", "a1", cancel_previous=True)
    token1 = pc.token_for(s1.session_id)
    assert token1.is_cancelled() is False

    pc.start_session("s2", "a2", cancel_previous=True)
    assert token1.is_cancelled() is True
    assert pc.current_session_id == "s2"
