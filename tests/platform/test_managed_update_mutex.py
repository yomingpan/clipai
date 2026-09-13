from pathlib import Path

from ClipAI.platform.managed_update_mutex import WindowsManagedUpdateGate


class _Lease:
    def close(self) -> None:
        return None


class _Gate:
    def __init__(self, lease) -> None:
        self.lease = lease

    def acquire(self):
        return self.lease


class _GateFactory:
    def __init__(self) -> None:
        self.names: list[str] = []
        self.lease = _Lease()

    def __call__(self, name: str):
        self.names.append(name)
        return _Gate(self.lease)


def test_managed_update_gate_uses_one_stable_mutex_identity_per_canonical_install_root(tmp_path: Path):
    factory = _GateFactory()
    install_root = (tmp_path / "Install").resolve()

    first = WindowsManagedUpdateGate(install_root, gate_factory=factory)
    second = WindowsManagedUpdateGate(install_root / ".." / "Install", gate_factory=factory)
    other = WindowsManagedUpdateGate(tmp_path / "Other", gate_factory=factory)

    assert first.acquire() is factory.lease
    assert second.acquire() is factory.lease
    assert other.acquire() is factory.lease
    assert factory.names[0] == factory.names[1]
    assert factory.names[0] != factory.names[2]
    assert factory.names[0].startswith("Local\\ClipAI.ManagedUpdate.v1.")
    assert len(factory.names[0].rsplit(".", 1)[1]) == 64
