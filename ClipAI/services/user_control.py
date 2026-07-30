from __future__ import annotations

from dataclasses import dataclass
import threading

from ClipAI.core.models import ControlSurfaceRef, InterruptibleOperationRef, InterruptionPlan


_GLOBAL_KINDS = frozenset(
    {"workflow", "speech", "copy", "paste", "archive", "shortcut_sequence"}
)


class InterruptibleOperationLease:
    def __init__(
        self,
        coordinator: UserControlCoordinator,
        key: tuple[str, str],
        generation: int,
    ) -> None:
        self._coordinator = coordinator
        self._key = key
        self._generation = generation

    def finish(self) -> None:
        self._coordinator._finish(self._key, self._generation)


@dataclass(frozen=True)
class _RegisteredOperation:
    sequence: int
    generation: int
    operation: InterruptibleOperationRef


class UserControlCoordinator:
    """Owns focused-control and interruptible-operation selection policy."""

    def __init__(self) -> None:
        self._focused: ControlSurfaceRef | None = None
        self._operations: dict[tuple[str, str], _RegisteredOperation] = {}
        self._sequence = 0
        self._generation = 0
        self._lock = threading.RLock()

    def focus(self, surface: ControlSurfaceRef) -> None:
        with self._lock:
            self._focused = surface

    @property
    def focused_surface(self) -> ControlSurfaceRef | None:
        with self._lock:
            return self._focused

    def release(self, surface: ControlSurfaceRef) -> None:
        with self._lock:
            if self._focused == surface:
                self._focused = None

    def begin(self, operation: InterruptibleOperationRef) -> InterruptibleOperationLease:
        key = (operation.kind, operation.operation_id)
        with self._lock:
            self._sequence += 1
            self._generation += 1
            registered = _RegisteredOperation(self._sequence, self._generation, operation)
            self._operations[key] = registered
        return InterruptibleOperationLease(self, key, registered.generation)

    def interrupt_current(self) -> InterruptionPlan:
        with self._lock:
            surface = self._focused
            if surface is not None:
                operations = self._claim(
                    lambda item: item.operation.surface_id == surface.surface_id
                )
                self._focused = None
                return InterruptionPlan(surface, operations)
            if not self._operations:
                return InterruptionPlan()
            current = max(self._operations.values(), key=lambda item: item.sequence)
            key = (current.operation.kind, current.operation.operation_id)
            self._operations.pop(key, None)
            return InterruptionPlan(operations=(current.operation,))

    def interrupt_all(self) -> InterruptionPlan:
        with self._lock:
            return InterruptionPlan(
                operations=self._claim(lambda item: item.operation.kind in _GLOBAL_KINDS)
            )

    def _claim(self, predicate) -> tuple[InterruptibleOperationRef, ...]:
        selected = tuple(
            item for item in self._operations.values() if predicate(item)
        )
        for item in selected:
            self._operations.pop(
                (item.operation.kind, item.operation.operation_id),
                None,
            )
        return tuple(
            item.operation for item in sorted(selected, key=lambda item: item.sequence)
        )

    def _finish(self, key: tuple[str, str], generation: int) -> None:
        with self._lock:
            current = self._operations.get(key)
            if current is not None and current.generation == generation:
                self._operations.pop(key, None)
