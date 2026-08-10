from __future__ import annotations

import pytest

from ClipAI.core.models import OutputOperationResult, UserFacingError
from ClipAI.ui.popup_external_output import FocusEntered, FocusPopup, OutsideFocusCheckRequested, OutsideFocusObserved, OutsidePointerPressed, OwnedDialogClosed, OwnedDialogOpened, PopupExternalOutputTransitions, PopupRegistered, PopupShown, PulseOutputAction, ReportControlSurfaceReleased, RequestPopupClose, ScheduleOutsideFocusCheck, SetFocusProjection, SetOutputActionEnabled, SetPopupVisibility, ShowOutputMessage


def ready_transitions() -> PopupExternalOutputTransitions:
    transitions = PopupExternalOutputTransitions()
    transitions.focus(PopupRegistered())
    transitions.focus(PopupShown())
    transitions.focus(FocusEntered())
    return transitions


@pytest.mark.parametrize(
    ("kind", "slot_id"),
    (("copy", "copy"), ("archive", "archive"), ("speech", "speaker")),
)
def test_non_paste_outputs_share_identity_and_success_feedback(kind, slot_id) -> None:
    transitions = ready_transitions()
    assert transitions.begin(kind, "current").accepted is True

    pending = transitions.acknowledge(OutputOperationResult("current", "w1", kind, "pending"))
    succeeded = transitions.acknowledge(OutputOperationResult("current", "w1", kind, "succeeded"))

    expected_pending = () if kind == "speech" else (SetOutputActionEnabled(slot_id, False),)
    assert pending == expected_pending
    if kind != "speech":
        assert SetOutputActionEnabled(slot_id, True) in succeeded
    assert PulseOutputAction(slot_id) in succeeded


def test_paste_success_is_not_a_legal_acknowledgement() -> None:
    with pytest.raises(ValueError, match="unsupported paste output-operation state"):
        OutputOperationResult("paste-op", "w1", "paste", "succeeded")


def test_archive_success_returns_conditional_confirmation() -> None:
    transitions = ready_transitions()
    transitions.begin("archive", "archive-op")

    actions = transitions.acknowledge(
        OutputOperationResult("archive-op", "w1", "archive", "succeeded")
    )

    assert ShowOutputMessage("已封存", 1000, only_when_overflow_collapsed=True) in actions


def test_stale_pending_and_terminal_acknowledgements_cannot_replace_current_operation() -> None:
    transitions = ready_transitions()
    transitions.begin("copy", "current")

    assert transitions.acknowledge(
        OutputOperationResult("old", "w1", "copy", "pending")
    ) == ()
    assert transitions.acknowledge(
        OutputOperationResult("old", "w1", "copy", "failed")
    ) == ()
    assert PulseOutputAction("copy") in transitions.acknowledge(
        OutputOperationResult("current", "w1", "copy", "succeeded")
    )


@pytest.mark.parametrize(
    ("state", "pinned", "expected_visibility"),
    (
        ("failed", False, "visible_activate"),
        ("failed", True, "visible_activate"),
        ("cancelled", False, "visible_no_activate"),
        ("cancelled", True, "visible_no_activate"),
        ("cleanup_failed", False, "visible_no_activate"),
        ("cleanup_failed", True, "visible_no_activate"),
        ("dispatched_unconfirmed", True, "visible_no_activate"),
        ("dispatched_unconfirmed", False, None),
    ),
)
def test_paste_terminal_visibility_matrix(state, pinned, expected_visibility) -> None:
    transitions = ready_transitions()
    begun = transitions.begin("paste", "paste-op", pinned=pinned)
    assert begun.actions == (
        SetFocusProjection(False),
        SetPopupVisibility("hidden"),
    )
    assert transitions.acknowledge(
        OutputOperationResult("paste-op", "w1", "paste", "pending")
    ) == (SetOutputActionEnabled("paste", False),)

    kwargs = {}
    if state == "failed":
        kwargs["error"] = UserFacingError("Paste failed")
    elif state in {"cleanup_failed", "dispatched_unconfirmed"}:
        kwargs["message"] = "Paste status"
    actions = transitions.acknowledge(
        OutputOperationResult("paste-op", "w1", "paste", state, **kwargs)
    )

    visibilities = [action.visibility for action in actions if isinstance(action, SetPopupVisibility)]
    assert visibilities == ([] if expected_visibility is None else [expected_visibility])
    assert SetOutputActionEnabled("paste", True) in actions


def test_paste_overlap_and_stale_completion_are_rejected_by_operation_identity() -> None:
    transitions = ready_transitions()
    assert transitions.begin("paste", "current").accepted is True
    assert transitions.begin("paste", "replacement").accepted is False
    assert transitions.acknowledge(
        OutputOperationResult("old", "w1", "paste", "cancelled")
    ) == ()


def test_paste_terminal_actions_restore_controls_before_visibility_and_feedback() -> None:
    transitions = ready_transitions()
    transitions.begin("paste", "paste-op")

    actions = transitions.acknowledge(OutputOperationResult(
        "paste-op",
        "w1",
        "paste",
        "failed",
        error=UserFacingError("Paste failed"),
    ))

    assert actions == (
        SetOutputActionEnabled("paste", True),
        SetPopupVisibility("visible_activate"),
        PulseOutputAction("paste", error=True),
        ShowOutputMessage("Paste failed", 1500),
    )


def test_focus_checks_wait_for_registration_show_and_initial_focus() -> None:
    transitions = PopupExternalOutputTransitions()
    assert transitions.focus(OutsideFocusCheckRequested()) == ()
    transitions.focus(PopupRegistered())
    transitions.focus(PopupShown())
    assert transitions.focus(OutsideFocusCheckRequested()) == ()
    transitions.focus(FocusEntered())

    scheduled = transitions.focus(OutsideFocusCheckRequested())

    assert len(scheduled) == 1
    assert isinstance(scheduled[0], ScheduleOutsideFocusCheck)
    assert transitions.focus(OutsideFocusCheckRequested()) == ()


def test_outside_pointer_press_closes_shown_popup_even_when_initial_focus_failed() -> None:
    transitions = PopupExternalOutputTransitions()
    transitions.focus(PopupRegistered())
    transitions.focus(PopupShown())

    assert transitions.focus(OutsidePointerPressed(pinned=False)) == (
        SetFocusProjection(False),
        ReportControlSurfaceReleased(),
        RequestPopupClose(),
    )


def test_outside_pointer_press_respects_pin_and_owned_dialog_guards() -> None:
    transitions = PopupExternalOutputTransitions()
    transitions.focus(PopupRegistered())
    transitions.focus(PopupShown())

    assert transitions.focus(OutsidePointerPressed(pinned=True)) == (
        SetFocusProjection(False),
        ReportControlSurfaceReleased(),
    )

    transitions.focus(OwnedDialogOpened())
    assert transitions.focus(OutsidePointerPressed(pinned=False)) == ()


def test_new_focus_invalidates_a_stale_outside_check_generation() -> None:
    transitions = ready_transitions()
    scheduled = transitions.focus(OutsideFocusCheckRequested())[0]
    assert isinstance(scheduled, ScheduleOutsideFocusCheck)

    transitions.focus(FocusEntered())

    assert transitions.focus(OutsideFocusObserved(
        scheduled.generation,
        pinned=False,
        focused_inside=False,
    )) == ()
    assert transitions.focused_inside is True


@pytest.mark.parametrize(
    ("pinned", "focused_inside", "expected_tail"),
    (
        (False, True, ()),
        (True, False, (ReportControlSurfaceReleased(),)),
        (False, False, (ReportControlSurfaceReleased(), RequestPopupClose())),
    ),
)
def test_outside_focus_observation_returns_semantic_ui_actions(
    pinned,
    focused_inside,
    expected_tail,
) -> None:
    transitions = ready_transitions()
    scheduled = transitions.focus(OutsideFocusCheckRequested())[0]
    assert isinstance(scheduled, ScheduleOutsideFocusCheck)

    actions = transitions.focus(OutsideFocusObserved(
        scheduled.generation,
        pinned=pinned,
        focused_inside=focused_inside,
    ))

    assert actions == (SetFocusProjection(focused_inside), *expected_tail)


def test_paste_begin_invalidates_and_suppresses_outside_focus_checks() -> None:
    transitions = ready_transitions()
    scheduled = transitions.focus(OutsideFocusCheckRequested())[0]
    assert isinstance(scheduled, ScheduleOutsideFocusCheck)

    transitions.begin("paste", "paste-op")

    assert transitions.focus(OutsideFocusObserved(
        scheduled.generation,
        pinned=False,
        focused_inside=False,
    )) == ()
    assert transitions.focus(OutsideFocusCheckRequested()) == ()


def test_owned_dialog_hold_and_restore_are_expressed_as_actions() -> None:
    transitions = ready_transitions()

    assert transitions.focus(OwnedDialogOpened()) == (SetFocusProjection(False),)
    assert transitions.focus(OutsideFocusCheckRequested()) == ()
    assert transitions.focus(OwnedDialogClosed(restored=True)) == (
        FocusPopup(),
        SetFocusProjection(True),
    )
