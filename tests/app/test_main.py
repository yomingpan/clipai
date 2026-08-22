from __future__ import annotations

import pytest

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
    monkeypatch.setattr(main, "load_config_bundle", lambda: (_ for _ in ()).throw(ConfigError("bad config")))
    monkeypatch.setattr(main, "show_startup_error", messages.append)

    with pytest.raises(SystemExit) as caught:
        main.main(instance_gate=InstanceGate(Lease()))

    assert caught.value.code == 2
    assert messages == ["bad config"]


def test_main_loads_dotenv_with_file_precedence(monkeypatch) -> None:
    calls: list[dict[str, bool]] = []
    runtime = type("Runtime", (), {"run_forever": lambda self: None})()
    monkeypatch.setattr(main, "load_dotenv", lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr(main, "load_config_bundle", lambda: object())
    monkeypatch.setattr(main, "build_runtime", lambda _bundle: runtime)

    main.main(instance_gate=InstanceGate(Lease()))

    assert calls == [{"override": True}]


def test_second_instance_stops_before_loading_configuration(monkeypatch) -> None:
    messages: list[str] = []
    configuration_loads: list[str] = []
    monkeypatch.setattr(main, "show_startup_error", messages.append)
    monkeypatch.setattr(main, "load_config_bundle", lambda: configuration_loads.append("loaded"))

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
    monkeypatch.setattr(main, "load_config_bundle", load_configuration)
    monkeypatch.setattr(main, "build_runtime", lambda _bundle: runtime)

    main.main()

    assert configuration_loads == []
