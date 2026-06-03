from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterator

import pytest

from tests.helpers.fake_clipboard import FakeClipboard
from tests.helpers.fake_event_bus import FakeEventBus
from tests.helpers.fake_provider import FakeProvider


@pytest.fixture(autouse=True)
def clean_global_state(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Keep unit tests isolated from long-lived application singletons."""
    from clipai.core import cancellation as cancellation_module
    from clipai.core import event_bus as event_bus_module

    event_bus_module._default_bus = None

    controller = cancellation_module.get_cancellation_controller()
    controller.clear_cancel_event()
    controller._interruptibles.clear()

    monkeypatch.delenv("CLIPAI_CONFIG_DIR", raising=False)

    yield

    event_bus_module._default_bus = None
    controller.clear_cancel_event()
    controller._interruptibles.clear()

    memory_module = sys.modules.get("clipai.memory_manager")
    if memory_module is not None and hasattr(memory_module, "_manager"):
        memory_module._manager = None


@pytest.fixture
def fake_provider() -> FakeProvider:
    return FakeProvider(content="fake response")


@pytest.fixture
def fake_event_bus() -> FakeEventBus:
    return FakeEventBus()


@pytest.fixture
def fake_clipboard() -> FakeClipboard:
    return FakeClipboard()


@pytest.fixture
def tmp_config_dir(tmp_path: Path) -> Path:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text("app: {}\nprovider: {}\ntts: {}\n", encoding="utf-8")
    (config_dir / "actions.yaml").write_text("actions: []\n", encoding="utf-8")
    return config_dir
