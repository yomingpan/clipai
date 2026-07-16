from __future__ import annotations

import pytest

from ClipAI.core.errors import ConfigError
import main


def test_config_error_uses_startup_error_surface(monkeypatch) -> None:
    messages: list[str] = []
    monkeypatch.setattr(main, "load_dotenv", None)
    monkeypatch.setattr(main, "load_config_bundle", lambda: (_ for _ in ()).throw(ConfigError("bad config")))
    monkeypatch.setattr(main, "show_startup_error", messages.append)

    with pytest.raises(SystemExit) as caught:
        main.main()

    assert caught.value.code == 2
    assert messages == ["bad config"]


def test_main_loads_dotenv_with_file_precedence(monkeypatch) -> None:
    calls: list[dict[str, bool]] = []
    runtime = type("Runtime", (), {"run_forever": lambda self: None})()
    monkeypatch.setattr(main, "load_dotenv", lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr(main, "load_config_bundle", lambda: object())
    monkeypatch.setattr(main, "build_runtime", lambda _bundle: runtime)

    main.main()

    assert calls == [{"override": True}]
