from __future__ import annotations

import pytest
from types import SimpleNamespace

from ClipAI.core.errors import ConfigError
import main


class Lease:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class InstanceGate:
    def __init__(self, lease: Lease | None) -> None:
        self.lease = lease

    def acquire(self) -> Lease | None:
        return self.lease


def test_config_error_uses_startup_error_surface(monkeypatch) -> None:
    messages: list[str] = []
    monkeypatch.setattr(main, "load_dotenv", None)
    monkeypatch.setattr(main, "bootstrap_action_language_config", lambda _store, **_paths: (_ for _ in ()).throw(ConfigError("bad config")))
    monkeypatch.setattr(main, "show_startup_error", messages.append)

    with pytest.raises(SystemExit) as caught:
        main.main(instance_gate=InstanceGate(Lease()))

    assert caught.value.code == 2
    assert messages == ["bad config"]


def test_main_loads_dotenv_with_file_precedence(monkeypatch) -> None:
    calls: list[tuple[object, bool]] = []
    runtime = type("Runtime", (), {"run_forever": lambda self: None})()
    monkeypatch.setattr(main, "load_dotenv", lambda path, *, override: calls.append((path, override)))
    monkeypatch.setattr(main, "bootstrap_action_language_config", lambda _store, **_paths: SimpleNamespace(bundle=object()))
    monkeypatch.setattr(main, "build_runtime", lambda _bundle, *, paths: runtime)

    main.main(instance_gate=InstanceGate(Lease()))

    assert len(calls) == 1
    assert calls[0][0].name == ".env"
    assert calls[0][1] is True


def test_second_instance_stops_before_loading_configuration(monkeypatch) -> None:
    messages: list[str] = []
    configuration_loads: list[str] = []
    monkeypatch.setattr(main, "show_startup_error", messages.append)
    monkeypatch.setattr(main, "bootstrap_action_language_config", lambda _store: configuration_loads.append("loaded"))

    main.main(instance_gate=InstanceGate(None))

    assert configuration_loads == []
    assert messages == ["ClipAI is already running."]


def test_main_uses_composed_instance_gate_before_loading_configuration(monkeypatch) -> None:
    configuration_loads: list[str] = []
    runtime = type("Runtime", (), {"run_forever": lambda self: None})()

    def load_configuration():
        configuration_loads.append("loaded")
        return object()

    monkeypatch.setattr(main, "build_application_instance_gate", lambda: InstanceGate(None), raising=False)
    monkeypatch.setattr(main, "show_startup_error", lambda _message: None)
    monkeypatch.setattr(main, "load_dotenv", None)
    monkeypatch.setattr(main, "bootstrap_action_language_config", lambda _store: SimpleNamespace(bundle=load_configuration()))
    monkeypatch.setattr(main, "build_runtime", lambda _bundle: runtime)

    main.main()

    assert configuration_loads == []
