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
