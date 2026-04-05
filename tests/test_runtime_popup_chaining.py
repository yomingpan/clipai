from __future__ import annotations

from clipai.app.config import AppConfigBundle
from clipai.app.runtime import DesktopRuntime
from clipai.services.popup_session import PopupSession


class _FakePresenter:
    def __init__(self, session_id: str | None, active: bool = True) -> None:
        self._session_id = session_id
        self._active = active

    def get_active_session_id(self) -> str | None:
        return self._session_id

    def is_session_active(self, session_id: str) -> bool:
        return self._active and self._session_id == session_id


def _bundle() -> AppConfigBundle:
    action = {
        "id": "summarize_next_steps",
        "name": "Summary",
        "prompt": "Summarize: {input}",
        "output_mode": "popup",
    }
    return AppConfigBundle(
        config_path="config/config.yaml",
        cfg={},
        app_cfg={},
        provider_cfg={},
        tts_cfg={},
        actions=[action],
        action_map={action["id"]: action},
    )


def test_runtime_uses_active_popup_session_for_chaining() -> None:
    runtime = DesktopRuntime(_bundle())
    session = PopupSession(
        action_id="summarize_next_steps",
        action_name="Summary",
        original_input="source text",
        latest_result="final popup output",
        input_loading=False,
        result_loading=False,
    )
    runtime._popup_sessions[session.session_id] = session
    runtime._popup_presenter = _FakePresenter(session.session_id)

    resolved = runtime._active_popup_chain_session()

    assert resolved is session


def test_runtime_skips_popup_chaining_when_popup_is_loading_or_empty() -> None:
    runtime = DesktopRuntime(_bundle())
    session = PopupSession(
        action_id="summarize_next_steps",
        action_name="Summary",
        original_input="source text",
        latest_result="",
        input_loading=False,
        result_loading=True,
    )
    runtime._popup_sessions[session.session_id] = session
    runtime._popup_presenter = _FakePresenter(session.session_id)

    assert runtime._active_popup_chain_session() is None
