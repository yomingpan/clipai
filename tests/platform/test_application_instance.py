from __future__ import annotations

import sys
import uuid

import pytest

from ClipAI.platform.application_instance import WindowsApplicationInstanceGate


class MutexApi:
    def __init__(self, *, handle: int, last_error: int) -> None:
        self.handle = handle
        self.last_error = last_error
        self.created_names: list[str] = []
        self.closed_handles: list[int] = []

    def create_mutex(self, _security, _initial_owner: bool, name: str) -> int:
        self.created_names.append(name)
        return self.handle

    def get_last_error(self) -> int:
        return self.last_error

    def close_handle(self, handle: int) -> None:
        self.closed_handles.append(handle)


def test_windows_instance_gate_holds_one_idempotent_lease() -> None:
    api = MutexApi(handle=41, last_error=0)
    gate = WindowsApplicationInstanceGate(
        "Local\\ClipAI.Tests",
        create_mutex=api.create_mutex,
        get_last_error=api.get_last_error,
        close_handle=api.close_handle,
    )

    lease = gate.acquire()
    assert lease is not None

    lease.close()
    lease.close()

    assert api.created_names == ["Local\\ClipAI.Tests"]
    assert api.closed_handles == [41]


def test_windows_instance_gate_rejects_an_existing_instance_and_closes_probe_handle() -> None:
    api = MutexApi(handle=42, last_error=183)
    gate = WindowsApplicationInstanceGate(
        "Local\\ClipAI.Tests",
        create_mutex=api.create_mutex,
        get_last_error=api.get_last_error,
        close_handle=api.close_handle,
    )

    assert gate.acquire() is None
    assert api.closed_handles == [42]


@pytest.mark.integration
@pytest.mark.skipif(sys.platform != "win32", reason="requires a Windows named mutex")
def test_windows_instance_gate_releases_the_real_session_mutex() -> None:
    name = f"Local\\ClipAI.Tests.{uuid.uuid4()}"
    first = WindowsApplicationInstanceGate(name)
    second = WindowsApplicationInstanceGate(name)

    first_lease = first.acquire()
    assert first_lease is not None
    assert second.acquire() is None

    first_lease.close()
    second_lease = second.acquire()
    assert second_lease is not None
    second_lease.close()
