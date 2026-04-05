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
