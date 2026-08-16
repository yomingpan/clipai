from __future__ import annotations

import pytest

from ClipAI.core.errors import PersonalStyleUnavailableError
from ClipAI.core.models import PersonalStyleCollection, ResolvedAction
from ClipAI.services.personal_styles import MAX_PERSONAL_STYLE_CHARACTERS, PersonalStyleCoordinator


class MemoryStore:
    def __init__(self, collection: PersonalStyleCollection = PersonalStyleCollection()) -> None:
        self.collection = collection
        self.saved: list[PersonalStyleCollection] = []

    def load(self) -> PersonalStyleCollection:
        return self.collection

    def save(self, collection: PersonalStyleCollection) -> None:
        self.saved.append(collection)
        self.collection = collection


class MemoryReader:
    def __init__(self, files: dict[str, str]) -> None:
        self.files = files

    def read_text(self, path: str) -> str:
        return self.files[path]


def action(mode: str | None = "informal") -> ResolvedAction:
    return ResolvedAction(
        "personal", "Personal", "system", "{input}", "short",
        "selection_or_clipboard", "popup", 0.2,
        version_id="action-version", personal_style_mode=mode,
    )


def complete_import(coordinator: PersonalStyleCoordinator, path: str, operation_id: str = "import-1") -> None:
    update = coordinator.begin_import(path, operation_id)
    assert update.work is not None
    error = coordinator.execute(update.work)
    coordinator.complete(operation_id, error)


def test_first_import_is_persisted_selected_and_bound_to_style_actions() -> None:
    store = MemoryStore()
    coordinator = PersonalStyleCoordinator(store, MemoryReader({"Yoming 寫作風格指南.md": "# 共通\n只改怎麼說。"}))

    complete_import(coordinator, "Yoming 寫作風格指南.md")

    state = coordinator.state
    assert state.operation_state == "succeeded"
    assert state.profiles[0].name == "Yoming 寫作風格指南"
    assert state.selected_profile_id == state.profiles[0].profile_id
    bound = coordinator.bind(action())
    assert bound.personal_style is not None
    assert bound.personal_style.guide == "# 共通\n只改怎麼說。"
    assert bound.version_id != "action-version"
    assert coordinator.bind_to(action(), bound.personal_style) == bound
    assert coordinator.bind(action(None)).personal_style is None


def test_reimporting_same_file_name_updates_profile_without_duplicating_it() -> None:
    reader = MemoryReader({"Yoming.md": "first"})
    store = MemoryStore()
    coordinator = PersonalStyleCoordinator(store, reader)
    complete_import(coordinator, "Yoming.md", "first")
    profile_id = coordinator.state.selected_profile_id
    reader.files["Yoming.md"] = "second"

    complete_import(coordinator, "Yoming.md", "second")

    assert len(store.collection.profiles) == 1
    assert store.collection.profiles[0].profile_id == profile_id
    assert store.collection.profiles[0].guide == "second"


def test_failed_import_keeps_previous_collection_active() -> None:
    store = MemoryStore()
    coordinator = PersonalStyleCoordinator(store, MemoryReader({"good.md": "style", "bad.md": "x" * (MAX_PERSONAL_STYLE_CHARACTERS + 1)}))
    complete_import(coordinator, "good.md", "good")
    previous = store.collection

    complete_import(coordinator, "bad.md", "bad")

    assert coordinator.state.operation_state == "failed"
    assert "too long" in coordinator.state.message
    assert store.collection == previous
    assert coordinator.bind(action()).personal_style == previous.profiles[0]


def test_only_one_profile_mutation_can_be_pending_and_late_completion_is_ignored() -> None:
    coordinator = PersonalStyleCoordinator(MemoryStore(), MemoryReader({"one.md": "style"}))
    first = coordinator.begin_import("one.md", "one")
    blocked = coordinator.begin_import("one.md", "two")
    late = coordinator.complete("old", "late")

    assert first.work is not None
    assert blocked.ignored is True
    assert late.ignored is True
    assert coordinator.state.operation_id == "one"


def test_style_action_without_active_profile_fails_before_execution() -> None:
    coordinator = PersonalStyleCoordinator(MemoryStore(), MemoryReader({}))

    with pytest.raises(PersonalStyleUnavailableError, match="尚未選擇個人風格"):
        coordinator.bind(action())


@pytest.mark.parametrize("path, content, message", [
    ("style.pdf", "words", "Markdown"),
    ("empty.txt", "   ", "empty"),
])
def test_import_rejects_unsupported_or_empty_guides(path: str, content: str, message: str) -> None:
    coordinator = PersonalStyleCoordinator(MemoryStore(), MemoryReader({path: content}))
    update = coordinator.begin_import(path, "import")
    assert update.work is not None
    error = coordinator.execute(update.work)
    coordinator.complete("import", error)
    assert coordinator.state.operation_state == "failed"
    assert message in coordinator.state.message
