from __future__ import annotations

from ClipAI.app.language_pack_loader import (
    ActionLanguagePackLoader,
    ActionLanguagePackRegistry,
)
from ClipAI.core.errors import ActionLanguagePackError, ActionLanguagePackErrorCode
from ClipAI.core.ports import ActionLanguagePackSelectionStore


class AppActionLanguageSelectionBackend:
    """Revalidates a candidate before atomically saving its next-start ID."""

    def __init__(
        self,
        loader: ActionLanguagePackLoader,
        registry: ActionLanguagePackRegistry,
        store: ActionLanguagePackSelectionStore,
    ) -> None:
        self._loader = loader
        self._registry = registry
        self._store = store

    def validate_and_save(
        self,
        pack_id: str,
    ) -> ActionLanguagePackErrorCode | None:
        try:
            entry = self._registry.entry(pack_id)
            self._loader.load(entry)
            self._store.save(pack_id)
        except ActionLanguagePackError as exc:
            return exc.reason
        except (OSError, ValueError):
            return "selection_save_failed"
        return None
