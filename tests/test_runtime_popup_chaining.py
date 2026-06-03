from __future__ import annotations

from clipai.app.config import AppConfigBundle
from clipai.app.runtime import DesktopRuntime
from clipai.services.popup_session import PopupSession


class _FakePresenter:
    def __init__(self, session_id: str | None, active: bool = True) -> None:
        self._session_id = session_id
        self._active = active
        self.disposed = False

    def get_active_session_id(self) -> str | None:
        return self._session_id

    def is_session_active(self, session_id: str) -> bool:
        return self._active and self._session_id == session_id

    def dispose(self) -> None:
        self.disposed = True


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


def test_runtime_close_popup_session_removes_cached_session() -> None:
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
    runtime._close_popup_session(session.session_id)

    assert session.session_id not in runtime._popup_sessions


def test_runtime_stop_disposes_presenter() -> None:
    runtime = DesktopRuntime(_bundle())
    runtime._run_state["running"] = True
    presenter = _FakePresenter(None)
    runtime._popup_presenter = presenter

    runtime.stop()

    assert presenter.disposed is True
    assert runtime._popup_presenter is None


def test_runtime_run_forever_uses_blocking_tray_loop() -> None:
    runtime = DesktopRuntime(_bundle())
    calls = []

    class _FakeTray:
        def run(self, *, detached: bool = True) -> None:
            calls.append(detached)
            runtime._run_state["running"] = False

        def stop(self) -> None:
            calls.append("stop")

    runtime._run_state["running"] = True
    runtime._tray = _FakeTray()

    runtime.run_forever()

    assert calls == [False]
