from __future__ import annotations

from clipai.services.popup_session import PopupSession


def test_popup_session_loading_flags_transition_cleanly() -> None:
    session = PopupSession(
        action_id="summarize_next_steps",
        action_name="Summary",
        original_input="",
        latest_result="",
        input_loading=True,
        result_loading=True,
    )

    session.mark_input_ready("input text")
    session.mark_result_ready("result text")

    assert session.original_input == "input text"
    assert session.latest_result == "result text"
    assert session.input_loading is False
    assert session.result_loading is False


def test_popup_session_follow_up_only_sets_result_loading() -> None:
    session = PopupSession(
        action_id="summarize_next_steps",
        action_name="Summary",
        original_input="source text",
        latest_result="initial result",
        input_loading=False,
        result_loading=False,
    )

    session.start_round(kind="follow_up", prompt_text="clarify", model="gemini")

    assert session.original_input == "source text"
    assert session.input_loading is False
    assert session.result_loading is True


def test_popup_session_begin_chained_action_reuses_session_with_new_metadata() -> None:
    session = PopupSession(
        action_id="summarize_next_steps",
        action_name="Summary",
        original_input="source text",
        latest_result="initial result",
        action_press_type="short",
        input_loading=False,
        result_loading=False,
    )

    session.begin_chained_action(
        action_id="translate_en",
        action_name="Translate EN",
        original_input="initial result",
        action_press_type="short",
        variant_applied=False,
        resolved_action_def={"id": "translate_en", "output_mode": "paste"},
    )

    assert session.action_id == "translate_en"
    assert session.action_name == "Translate EN"
    assert session.original_input == "initial result"
    assert session.latest_result == "Connecting..."
    assert session.input_loading is False
    assert session.result_loading is True


def test_popup_session_append_result_chunk_clears_loading_placeholder_once() -> None:
    session = PopupSession(
        action_id="summarize_next_steps",
        action_name="Summary",
        original_input="source text",
        latest_result="Connecting...",
        input_loading=False,
        result_loading=True,
    )

    session.append_result_chunk("Hello")
    session.append_result_chunk(" world")

    assert session.latest_result == "Hello world"
    assert session.result_loading is False


def test_popup_session_snapshot_is_safe_for_rendering() -> None:
    session = PopupSession(
        action_id="summarize_next_steps",
        action_name="Summary",
        original_input="source text",
        latest_result="final popup output",
        input_loading=False,
        result_loading=False,
    )

    snapshot = session.snapshot()

    assert snapshot.action_id == "summarize_next_steps"
    assert snapshot.latest_result == "final popup output"
    assert snapshot.can_continue() is True


def test_popup_session_tracks_current_result_metadata() -> None:
    session = PopupSession(
        action_id="summarize_next_steps",
        action_name="Summary",
        original_input="source text",
        latest_result="final popup output",
    )

    session.update_result_metadata(provider="gemini", model="gemini-3.1-flash-lite-preview")
    snapshot = session.snapshot()

    assert snapshot.current_provider == "gemini"
    assert snapshot.current_model == "gemini-3.1-flash-lite-preview"
