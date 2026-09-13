from __future__ import annotations

from collections.abc import Callable
from hashlib import sha256
from pathlib import Path

from ClipAI.core.update_ports import ManagedUpdateGate, ManagedUpdateLease
from ClipAI.platform.application_instance import WindowsNamedMutexGate
from ClipAI.platform.managed_update_fs import canonical_path


NamedGateFactory = Callable[[str], ManagedUpdateGate]


class WindowsManagedUpdateGate:
    """Derive one stable session mutex from the canonical managed install root."""

    def __init__(
        self,
        install_root: str | Path,
        *,
        gate_factory: NamedGateFactory = WindowsNamedMutexGate,
    ) -> None:
        identity = str(canonical_path(install_root)).casefold().encode("utf-8")
        digest = sha256(identity).hexdigest()
        self._gate = gate_factory(f"Local\\ClipAI.ManagedUpdate.v1.{digest}")

    def acquire(self) -> ManagedUpdateLease | None:
        return self._gate.acquire()
