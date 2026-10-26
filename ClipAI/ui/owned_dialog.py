from __future__ import annotations

from collections.abc import Callable
from typing import Generic, Protocol, TypeVar


class _ClosableDialog(Protocol):
    def close(self) -> object: ...

    def destroy(self) -> object: ...


TDialog = TypeVar("TDialog", bound=_ClosableDialog)
TState = TypeVar("TState")


class OwnedDialogSlot(Generic[TDialog]):
    """Own one lazily-built auxiliary dialog and its terminal lifecycle."""

    def __init__(self, factory: Callable[[], TDialog | None]) -> None:
        self._factory = factory
        self._instance: TDialog | None = None

    @property
    def instance(self) -> TDialog | None:
        return self._instance

    def ensure(self) -> TDialog | None:
        if self._instance is None:
            self._instance = self._factory()
        return self._instance

    def present(self, use: Callable[[TDialog], object]) -> bool:
        instance = self.ensure()
        if instance is None:
            return False
        use(instance)
        return True

    def update(self, use: Callable[[TDialog], object]) -> bool:
        instance = self._instance
        if instance is None:
            return False
        use(instance)
        return True

    def close(self, *, forget: bool = False) -> bool:
        instance = self._instance
        if instance is None:
            return False
        instance.close()
        if forget:
            self._instance = None
        return True

    def destroy(self) -> bool:
        instance = self._instance
        if instance is None:
            return False
        try:
            instance.destroy()
        finally:
            self._instance = None
        return True
