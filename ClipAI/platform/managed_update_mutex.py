from __future__ import annotations

from collections.abc import Callable
from hashlib import sha256
from pathlib import Path

from ClipAI.core.update_ports import ManagedUpdateGate, ManagedUpdateLease
from ClipAI.core.managed_update import FailureCode, ManagedUpdateFailure
from ClipAI.platform.application_instance import WindowsNamedMutexGate
from ClipAI.platform.managed_update_fs import canonical_path


NamedGateFactory = Callable[[str], ManagedUpdateGate]


class WindowsManagedUpdateGate:
    """Derive one cross-session mutex from the canonical managed install root."""

    def __init__(
        self,
        install_root: str | Path,
        *,
        gate_factory: NamedGateFactory = WindowsNamedMutexGate,
    ) -> None:
        identity = str(canonical_path(install_root)).casefold().encode("utf-8")
        digest = sha256(identity).hexdigest()
        self._gate = gate_factory(f"Global\\ClipAI.ManagedUpdate.v1.{digest}")

    def acquire(self) -> ManagedUpdateLease | None:
        return self._gate.acquire()


class ManagedInstallationAdmission:
    """A live root-bound capability shared by install and native settlement."""

    def __init__(self, root: Path, lease: ManagedUpdateLease) -> None:
        self._root = canonical_path(root)
        self._lease: ManagedUpdateLease | None = lease

    def require_active(self, install_root: Path) -> None:
        if self._lease is None or canonical_path(install_root) != self._root:
            raise ManagedUpdateFailure(FailureCode.IDENTITY_INELIGIBLE, "installation admission is not active")

    def close(self) -> None:
        lease, self._lease = self._lease, None
        if lease is not None:
            lease.close()


def admit_installation(root: Path, gate_factory=WindowsManagedUpdateGate) -> ManagedInstallationAdmission:
    lease = gate_factory(root).acquire()
    if lease is None:
        raise ManagedUpdateFailure(FailureCode.UPDATE_BUSY, "managed installation is busy")
    return ManagedInstallationAdmission(root, lease)
