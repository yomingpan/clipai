from __future__ import annotations

from ClipAI.core.models import ManagedUpdatePresentation
from ClipAI.ui.owned_modals import OwnedModalRegistry


def test_about_dialog_receives_version_github_and_latest_managed_update(monkeypatch) -> None:
    import ClipAI.ui.owned_modals as module

    created = []

    class About:
        def __init__(self, _root, _sink, _native, **kwargs) -> None:
            created.append(kwargs)
            self.updates = []
        def set_managed_update(self, state) -> None: self.updates.append(state)
        def close(self) -> None: pass

    monkeypatch.setattr(module, "AboutDialog", About)
    registry = OwnedModalRegistry(object(), lambda _command: None, object(), version="1.2.3", github_url="https://example.com")
    state = ManagedUpdatePresentation("unavailable", "Unavailable", False)
    registry.set_managed_update(state)
    registry.show_about()
    assert created == [{"version": "1.2.3", "github_url": "https://example.com", "managed_update": state}]
