from ClipAI.app.language_pack_selection_backend import (
    AppActionLanguageSelectionBackend,
)
from ClipAI.core.errors import ActionLanguagePackError


class Registry:
    def __init__(self, events) -> None:
        self.events = events

    def entry(self, pack_id):
        self.events.append(("resolve", pack_id))
        return object()


class Loader:
    def __init__(self, events, error=None) -> None:
        self.events = events
        self.error = error

    def load(self, _entry):
        self.events.append(("validate",))
        if self.error is not None:
            raise self.error


class Store:
    def __init__(self, events, error=None) -> None:
        self.events = events
        self.error = error

    def load(self):
        raise AssertionError("unused")

    def save(self, pack_id):
        self.events.append(("save", pack_id))
        if self.error is not None:
            raise self.error


def test_backend_revalidates_before_saving() -> None:
    events = []
    backend = AppActionLanguageSelectionBackend(
        Loader(events),
        Registry(events),
        Store(events),
    )

    assert backend.validate_and_save("ja-JP") is None
    assert events == [("resolve", "ja-JP"), ("validate",), ("save", "ja-JP")]


def test_validation_failure_never_saves() -> None:
    events = []
    backend = AppActionLanguageSelectionBackend(
        Loader(
            events,
            ActionLanguagePackError(
                "checksum_mismatch",
                "resources.actions",
                "invalid pack",
            ),
        ),
        Registry(events),
        Store(events),
    )

    assert backend.validate_and_save("ja-JP") == "checksum_mismatch"
    assert events == [("resolve", "ja-JP"), ("validate",)]


def test_store_failure_maps_to_stable_error_code() -> None:
    events = []
    backend = AppActionLanguageSelectionBackend(
        Loader(events),
        Registry(events),
        Store(events, OSError("disk full")),
    )

    assert backend.validate_and_save("ja-JP") == "selection_save_failed"
